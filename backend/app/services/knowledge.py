"""Knowledge base management (MinIO = document, PostgreSQL = metadata/versions, ChromaDB = derived index)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.errors import Conflict
from app.models import FileObject, KnowledgeDocument, KnowledgeDocumentVersion
from app.services.files import DOC_MIME, store_file, validate_upload
from app.services.tenancy import get_scoped
from storage.minio.keys import knowledge_key


def create_document(db: Session, user: CurrentUser, *, data: bytes, filename: str | None, title: str,
                    document_type: str, description: str | None, role: str | None, topic: str | None,
                    skill: str | None, difficulty: str | None) -> tuple[KnowledgeDocument, KnowledgeDocumentVersion]:
    vf = validate_upload(data, filename, allowed=DOC_MIME, max_mb=get_settings().max_upload_mb)
    doc = KnowledgeDocument(institute_id=user.institute_id, title=title, description=description,
                            document_type=document_type, role=role, topic=topic, skill=skill, difficulty=difficulty,
                            current_version=1, status="active", created_by=user.id)
    db.add(doc)
    db.flush()
    f = store_file(db, vf, key=knowledge_key(user.institute_id, doc.id, 1, vf.ext), owner_id=user.id,
                   institute_id=user.institute_id, file_type="knowledge")
    doc.source_file_id = f.id
    v = KnowledgeDocumentVersion(document_id=doc.id, institute_id=user.institute_id, version=1, source_file_id=f.id,
                                 checksum=vf.checksum)
    db.add(v)
    db.flush()
    return doc, v


def add_version(db: Session, user: CurrentUser, doc_id: uuid.UUID, data: bytes, filename: str | None) -> KnowledgeDocumentVersion:
    doc = get_scoped(db, KnowledgeDocument, doc_id, user, label="Document")
    if doc.status == "deleted":
        raise Conflict("Document is deleted")
    vf = validate_upload(data, filename, allowed=DOC_MIME, max_mb=get_settings().max_upload_mb)
    latest = db.execute(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.document_id == doc.id)
                        .order_by(KnowledgeDocumentVersion.version.desc())).scalars().first()
    if latest and latest.checksum == vf.checksum:
        raise Conflict("This file is identical to the current version")
    n = (latest.version if latest else 0) + 1
    f = store_file(db, vf, key=knowledge_key(user.institute_id, doc.id, n, vf.ext), owner_id=user.id,
                   institute_id=user.institute_id, file_type="knowledge")
    v = KnowledgeDocumentVersion(document_id=doc.id, institute_id=user.institute_id, version=n, source_file_id=f.id,
                                 checksum=vf.checksum)
    db.add(v)
    doc.current_version = n
    doc.source_file_id = f.id
    db.flush()
    return v


def current_version(db: Session, doc: KnowledgeDocument) -> KnowledgeDocumentVersion | None:
    return db.execute(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.document_id == doc.id,
                                                             KnowledgeDocumentVersion.version == doc.current_version)).scalar_one_or_none()


def soft_delete(db: Session, user: CurrentUser, doc_id: uuid.UUID) -> KnowledgeDocument:
    from rag.ingestion.pipeline import remove_document

    doc = get_scoped(db, KnowledgeDocument, doc_id, user, label="Document")
    doc.status = "deleted"
    remove_document(doc.institute_id, doc.id)
    for v in db.execute(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.document_id == doc.id)).scalars():
        v.indexing_status = "removed"
    from app.models.base import utcnow

    for f in db.execute(select(FileObject).join(KnowledgeDocumentVersion, KnowledgeDocumentVersion.source_file_id == FileObject.id)
                        .where(KnowledgeDocumentVersion.document_id == doc.id)).scalars():
        f.deleted_at = utcnow()  # blobs retained for audit; inaccessible via API
    db.flush()
    return doc
