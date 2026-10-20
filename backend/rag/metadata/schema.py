"""Chunk metadata contract linking every vector back to PostgreSQL + MinIO (traceability, re-indexing)."""
from __future__ import annotations


def chunk_metadata(*, doc, version, chunk_id: str, chunk_index: int, embedding_model: str, embedding_version: str,
                   source_key: str) -> dict:  # noqa: ANN001
    return {
        "doc_id": str(doc.id),
        "institute_id": str(doc.institute_id),
        "source_key": source_key,
        "version": int(version.version),
        "version_id": str(version.id),
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "source_title": doc.title,
        "topic": doc.topic,
        "skill": doc.skill,
        "role": doc.role,
        "role_key": _key(doc.role),
        "difficulty": doc.difficulty,
        "content_type": doc.document_type,
        "active": doc.status == "active",
    }


def _key(v: str | None) -> str | None:
    from app.domain.text import normalize_key

    return normalize_key(v) if v else None
