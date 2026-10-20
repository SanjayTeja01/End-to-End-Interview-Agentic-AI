"""Vector store abstraction over ChromaDB (a DERIVED, disposable index).

Every query REQUIRES an institute_id — unrestricted retrieval is impossible by construction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings


class TenantFilterMissing(ValueError):
    pass


@dataclass
class VectorHit:
    chunk_id: str
    text: str
    metadata: dict
    score: float  # cosine similarity 0..1


class VectorStore(Protocol):
    def upsert(self, ids: list[str], embeddings: list[list[float]], texts: list[str], metadatas: list[dict]) -> None: ...
    def query(self, embedding: list[float], *, institute_id: str, filters: dict | None, k: int) -> list[VectorHit]: ...
    def delete(self, *, institute_id: str, doc_id: str | None = None, version: int | None = None) -> None: ...
    def reset(self) -> None: ...
    def count(self, *, institute_id: str | None = None) -> int: ...
    def ping(self) -> bool: ...


def _sanitize(meta: dict) -> dict:
    """Chroma metadata values must be scalar and non-null."""
    out = {}
    for k, v in meta.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    return out


def _where(institute_id: str, filters: dict | None) -> dict:
    if not institute_id:
        raise TenantFilterMissing("institute_id filter is mandatory for every vector query")
    clauses = [{"institute_id": str(institute_id)}]
    for k, v in (filters or {}).items():
        if v is None or k == "institute_id":
            continue
        clauses.append({k: {"$in": list(v)}} if isinstance(v, (list, tuple, set)) else {k: v})
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


class ChromaVectorStore:
    def __init__(self) -> None:
        import chromadb

        s = get_settings()
        self._client = chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port)
        self._name = s.chroma_collection
        self._col = self._client.get_or_create_collection(self._name, metadata={"hnsw:space": "cosine"})

    def upsert(self, ids, embeddings, texts, metadatas) -> None:  # noqa: ANN001
        for m in metadatas:
            if not m.get("institute_id"):
                raise TenantFilterMissing("chunk metadata must include institute_id")
        self._col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=[_sanitize(m) for m in metadatas])

    def query(self, embedding, *, institute_id, filters, k) -> list[VectorHit]:  # noqa: ANN001
        res = self._col.query(query_embeddings=[embedding], n_results=k, where=_where(institute_id, filters),
                              include=["documents", "metadatas", "distances"])
        hits = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            if str(meta.get("institute_id")) != str(institute_id):  # defence in depth
                continue
            hits.append(VectorHit(chunk_id=cid, text=doc, metadata=meta, score=round(1 - float(dist), 4)))
        return hits

    def delete(self, *, institute_id, doc_id=None, version=None) -> None:  # noqa: ANN001
        f = {}
        if doc_id:
            f["doc_id"] = str(doc_id)
        if version is not None:
            f["version"] = int(version)
        self._col.delete(where=_where(institute_id, f))

    def reset(self) -> None:
        try:
            self._client.delete_collection(self._name)
        except Exception:  # noqa: BLE001
            pass
        self._col = self._client.get_or_create_collection(self._name, metadata={"hnsw:space": "cosine"})

    def count(self, *, institute_id=None) -> int:  # noqa: ANN001
        if institute_id is None:
            return self._col.count()
        return len(self._col.get(where={"institute_id": str(institute_id)}, include=[])["ids"])

    def ping(self) -> bool:
        try:
            self._client.heartbeat()
            return True
        except Exception:  # noqa: BLE001
            return False


class InMemoryVectorStore:
    """Test double implementing identical filtering semantics."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[list[float], str, dict]] = {}

    def upsert(self, ids, embeddings, texts, metadatas) -> None:  # noqa: ANN001
        for i, e, t, m in zip(ids, embeddings, texts, metadatas):
            if not m.get("institute_id"):
                raise TenantFilterMissing("chunk metadata must include institute_id")
            self.rows[i] = (e, t, _sanitize(m))

    @staticmethod
    def _match(meta: dict, institute_id: str, filters: dict | None) -> bool:
        if str(meta.get("institute_id")) != str(institute_id):
            return False
        for k, v in (filters or {}).items():
            if v is None:
                continue
            if isinstance(v, (list, tuple, set)):
                if meta.get(k) not in v:
                    return False
            elif meta.get(k) != v:
                return False
        return True

    def query(self, embedding, *, institute_id, filters, k) -> list[VectorHit]:  # noqa: ANN001
        _where(institute_id, filters)  # same validation as Chroma
        scored = []
        for cid, (e, t, m) in self.rows.items():
            if self._match(m, institute_id, filters):
                sim = sum(a * b for a, b in zip(e, embedding)) / ((math.sqrt(sum(a * a for a in e)) or 1) * (math.sqrt(sum(b * b for b in embedding)) or 1))
                scored.append(VectorHit(cid, t, m, round(sim, 4)))
        return sorted(scored, key=lambda h: -h.score)[:k]

    def delete(self, *, institute_id, doc_id=None, version=None) -> None:  # noqa: ANN001
        f = {"doc_id": str(doc_id) if doc_id else None, "version": version}
        for cid in [c for c, (_, _, m) in self.rows.items() if self._match(m, institute_id, f)]:
            del self.rows[cid]

    def reset(self) -> None:
        self.rows.clear()

    def count(self, *, institute_id=None) -> int:  # noqa: ANN001
        return sum(1 for _, _, m in self.rows.values() if institute_id is None or m.get("institute_id") == str(institute_id))

    def ping(self) -> bool:
        return True


_override: VectorStore | None = None


def set_vector_store(v: VectorStore | None) -> None:
    global _override
    _override = v
    _default.cache_clear()


@lru_cache
def _default() -> VectorStore:
    return ChromaVectorStore()


def get_vector_store() -> VectorStore:
    return _override or _default()
