"""Tenant-aware retrieval. The institution context is always applied; callers cannot opt out."""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict

from app.core.logging import log_event
from app.domain.text import normalize_key
from rag.embeddings.providers import get_embeddings
from rag.retrieval.vector_store import VectorHit, get_vector_store

log = logging.getLogger(__name__)


def retrieve(*, institute_id: uuid.UUID | str, query: str, role: str | None = None, topic: str | None = None,
             skill: str | None = None, document_type: str | None = None, doc_ids: list[str] | None = None,
             k: int = 5, min_score: float = 0.2) -> list[VectorHit]:
    if not institute_id:
        raise ValueError("institute_id is required")
    store = get_vector_store()
    vec = get_embeddings().embed_query(query)
    base: dict = {"active": True}
    if document_type:
        base["content_type"] = document_type
    if doc_ids:
        base["doc_id"] = [str(d) for d in doc_ids]
    if skill:
        base_skill = {**base, "skill": skill}
    else:
        base_skill = None

    hits: list[VectorHit] = []
    seen: set[str] = set()
    # Most specific first, then broaden — never broaden beyond the tenant.
    attempts = []
    if role:
        attempts.append({**base, "role_key": normalize_key(role)})
    if base_skill:
        attempts.append(base_skill)
    attempts.append(base)
    for filters in attempts:
        for h in store.query(vec, institute_id=str(institute_id), filters=filters, k=k):
            if h.chunk_id not in seen and h.score >= min_score:
                seen.add(h.chunk_id)
                hits.append(h)
        if len(hits) >= k:
            break
    hits = sorted(hits, key=lambda h: -h.score)[:k]
    log_event(log, "rag_retrieval", institute_id=str(institute_id), hits=len(hits), topic=topic, role=role)
    return hits


def hits_to_context(hits: list[VectorHit], max_chars: int = 4000) -> tuple[str, list[dict]]:
    parts, sources, used = [], [], 0
    for h in hits:
        snippet = h.text[: max(0, max_chars - used)]
        if not snippet:
            break
        used += len(snippet)
        parts.append(f"[{h.metadata.get('source_title', 'source')} v{h.metadata.get('version')}]\n{snippet}")
        sources.append({"chunk_id": h.chunk_id, "doc_id": h.metadata.get("doc_id"), "title": h.metadata.get("source_title"),
                        "version": h.metadata.get("version"), "score": h.score})
    return "\n\n---\n\n".join(parts), sources


def hit_dict(h: VectorHit) -> dict:
    return asdict(h)
