"""Rebuild the ChromaDB index entirely from PostgreSQL metadata + MinIO source documents."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument, KnowledgeDocumentVersion
from rag.embeddings.providers import get_embeddings
from rag.ingestion.pipeline import ingest_version
from rag.retrieval.vector_store import get_vector_store

log = logging.getLogger(__name__)


def current_versions(db: Session, institute_id: uuid.UUID | None = None) -> list[KnowledgeDocumentVersion]:
    q = (select(KnowledgeDocumentVersion)
         .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeDocumentVersion.document_id)
         .where(KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.version == KnowledgeDocument.current_version))
    if institute_id:
        q = q.where(KnowledgeDocument.institute_id == institute_id)
    return list(db.execute(q).scalars())


def stale_versions(db: Session) -> list[KnowledgeDocumentVersion]:
    """Versions embedded with a different model/version than currently configured."""
    emb = get_embeddings()
    return [v for v in current_versions(db) if v.embedding_model != emb.model or v.embedding_version != emb.version]


def reindex_all(db: Session, *, institute_id: uuid.UUID | None = None, reset: bool = False, only_stale: bool = False) -> dict:
    store = get_vector_store()
    if reset and institute_id is None:
        store.reset()
    elif reset and institute_id:
        for v in current_versions(db, institute_id):
            store.delete(institute_id=str(institute_id), doc_id=str(v.document_id))
    versions = stale_versions(db) if only_stale else current_versions(db, institute_id)
    ok, failed, chunks = 0, 0, 0
    for v in versions:
        try:
            chunks += ingest_version(db, v.id)
            ok += 1
        except Exception:  # noqa: BLE001 — continue with the rest, failure is recorded on the version
            failed += 1
    summary = {"documents": len(versions), "indexed": ok, "failed": failed, "chunks": chunks}
    log.info("reindex_complete", extra={"data": summary})
    return summary
