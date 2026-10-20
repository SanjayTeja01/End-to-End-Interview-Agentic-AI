"""RAG ingestion: MinIO document + PostgreSQL metadata → extract → clean → chunk → embed → ChromaDB."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models import FileObject, KnowledgeDocument, KnowledgeDocumentVersion
from app.models.base import utcnow
from rag.chunking.chunker import chunk_text
from rag.cleaning.cleaner import clean_text
from rag.embeddings.providers import get_embeddings
from rag.extraction.extractors import extract
from rag.metadata.schema import chunk_metadata
from rag.retrieval.vector_store import get_vector_store
from storage.minio.client import get_storage

log = logging.getLogger(__name__)


def ingest_version(db: Session, version_id: uuid.UUID) -> int:
    """Index one document version. Idempotent: re-running replaces that document's vectors."""
    version = db.get(KnowledgeDocumentVersion, version_id)
    if version is None:
        raise ValueError("version not found")
    doc = db.get(KnowledgeDocument, version.document_id)
    file = db.get(FileObject, version.source_file_id)
    store = get_vector_store()
    version.processing_status = "processing"
    version.indexing_status = "processing"
    version.error = None
    db.commit()
    try:
        data = get_storage().get_bytes(file.object_key)
        ext = file.object_key.rsplit(".", 1)[-1]
        extracted = extract(data, ext)
        text = clean_text(extracted.text)
        version.processing_status = "completed"
        chunks = chunk_text(text, doc_id=str(doc.id), version=version.version)
        emb = get_embeddings()
        vectors = emb.embed_documents([c.text for c in chunks]) if chunks else []
        metas = [chunk_metadata(doc=doc, version=version, chunk_id=c.chunk_id, chunk_index=c.index,
                                embedding_model=emb.model, embedding_version=emb.version, source_key=file.object_key)
                 for c in chunks]
        # Only the current version of a document is retrievable: drop all previous vectors for this doc.
        store.delete(institute_id=str(doc.institute_id), doc_id=str(doc.id))
        if chunks and doc.status == "active":
            store.upsert([c.chunk_id for c in chunks], vectors, [c.text for c in chunks], metas)
        version.chunk_count = len(chunks)
        version.embedding_model, version.embedding_version = emb.model, emb.version
        version.indexing_status = "completed" if doc.status == "active" else "skipped_inactive"
        version.indexed_at = utcnow()
        for other in db.execute(select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.document_id == doc.id, KnowledgeDocumentVersion.id != version.id)).scalars():
            if other.indexing_status == "completed":
                other.indexing_status = "superseded"
        db.commit()
        log_event(log, "rag_document_indexed", doc_id=str(doc.id), version=version.version, chunks=len(chunks),
                  institute_id=str(doc.institute_id))
        return len(chunks)
    except Exception as exc:
        db.rollback()
        version = db.get(KnowledgeDocumentVersion, version_id)
        if version.processing_status == "processing":
            version.processing_status = "failed"
        version.indexing_status = "failed"
        version.error = str(exc)[:1000]
        db.commit()
        log.exception("rag_index_failed", extra={"data": {"version_id": str(version_id)}})
        raise


def remove_document(institute_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    get_vector_store().delete(institute_id=str(institute_id), doc_id=str(doc_id))
