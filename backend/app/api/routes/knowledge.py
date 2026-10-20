from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_institution
from app.core.database import get_db
from app.core.errors import ValidationFailed
from app.models import KnowledgeDocument, KnowledgeDocumentVersion
from app.schemas.common import JobOut
from app.schemas.knowledge import KnowledgeDocumentDetail, KnowledgeDocumentOut, KnowledgeUpdateIn, KnowledgeVersionOut, RagHit, RagQueryIn
from app.services import jobs
from app.services import knowledge as svc
from app.services.files import presigned_url_for
from app.services.tenancy import get_scoped

router = APIRouter(tags=["knowledge"])
DOC_TYPES = {"job_description", "role_document", "interview_guideline", "technical", "question_bank", "institution_info",
             "domain_info", "evaluation_guideline", "other"}


def _enqueue_index(db: Session, user: CurrentUser, version: KnowledgeDocumentVersion) -> dict:
    from app.workers.rag_tasks import index_document_version

    job = jobs.create_job(db, institute_id=user.institute_id, owner_id=user.id, job_type="rag_indexing",
                          entity_type="knowledge_document_version", entity_id=version.id)
    jobs.dispatch(index_document_version, str(version.id), str(job.id), job=job, db=db)
    return JobOut.model_validate(job).model_dump(mode="json")


def _doc_out(db: Session, doc: KnowledgeDocument, detail: bool = False) -> dict:
    model = KnowledgeDocumentDetail if detail else KnowledgeDocumentOut
    o = model.model_validate(doc)
    v = svc.current_version(db, doc)
    o.latest = KnowledgeVersionOut.model_validate(v) if v else None
    if detail:
        o.versions = [KnowledgeVersionOut.model_validate(x) for x in db.execute(
            select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.document_id == doc.id)
            .order_by(KnowledgeDocumentVersion.version.desc())).scalars()]
    return o.model_dump(mode="json")


@router.post("/knowledge/documents", status_code=202)
async def upload(file: UploadFile = File(...), title: str = Form(..., max_length=255), document_type: str = Form(...),
                 description: str | None = Form(default=None), role: str | None = Form(default=None),
                 topic: str | None = Form(default=None), skill: str | None = Form(default=None),
                 difficulty: str | None = Form(default=None), user: CurrentUser = Depends(require_institution),
                 db: Session = Depends(get_db)) -> dict:
    if document_type not in DOC_TYPES:
        raise ValidationFailed(f"document_type must be one of {sorted(DOC_TYPES)}")
    if difficulty and difficulty not in ("easy", "medium", "hard"):
        raise ValidationFailed("difficulty must be easy, medium or hard")
    doc, v = svc.create_document(db, user, data=await file.read(), filename=file.filename, title=title,
                                 document_type=document_type, description=description, role=role, topic=topic,
                                 skill=skill, difficulty=difficulty)
    db.commit()
    job = _enqueue_index(db, user, v)
    return {"document": _doc_out(db, doc), "job": job}


@router.get("/knowledge/documents")
def list_docs(user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> list[dict]:
    docs = db.execute(select(KnowledgeDocument).where(KnowledgeDocument.institute_id == user.institute_id,
                                                      KnowledgeDocument.status != "deleted")
                      .order_by(KnowledgeDocument.updated_at.desc())).scalars()
    return [_doc_out(db, d) for d in docs]


@router.get("/knowledge/documents/{doc_id}")
def get_doc(doc_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    return _doc_out(db, get_scoped(db, KnowledgeDocument, doc_id, user, label="Document"), detail=True)


@router.put("/knowledge/documents/{doc_id}")
def update_doc(doc_id: uuid.UUID, data: KnowledgeUpdateIn, user: CurrentUser = Depends(require_institution),
               db: Session = Depends(get_db)) -> dict:
    doc = get_scoped(db, KnowledgeDocument, doc_id, user, label="Document")
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(doc, k, v)
    db.commit()
    # Metadata lives on every chunk, so re-index to keep filters (role/topic/status) consistent.
    v = svc.current_version(db, doc)
    job = _enqueue_index(db, user, v) if v and changes else None
    return {"document": _doc_out(db, doc, detail=True), "job": job}


@router.post("/knowledge/documents/{doc_id}/versions", status_code=202)
async def new_version(doc_id: uuid.UUID, file: UploadFile = File(...), user: CurrentUser = Depends(require_institution),
                      db: Session = Depends(get_db)) -> dict:
    v = svc.add_version(db, user, doc_id, await file.read(), file.filename)
    db.commit()
    job = _enqueue_index(db, user, v)
    return {"document": _doc_out(db, db.get(KnowledgeDocument, doc_id), detail=True), "job": job}


@router.delete("/knowledge/documents/{doc_id}", status_code=204)
def delete_doc(doc_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> None:
    svc.soft_delete(db, user, doc_id)
    db.commit()


@router.post("/knowledge/documents/{doc_id}/reindex", status_code=202)
def reindex(doc_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    doc = get_scoped(db, KnowledgeDocument, doc_id, user, label="Document")
    v = svc.current_version(db, doc)
    return _enqueue_index(db, user, v)


@router.post("/knowledge/reindex", status_code=202)
def reindex_all(user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    """Rebuild this institution's portion of the vector index from PostgreSQL + MinIO."""
    from app.workers.rag_tasks import reindex_institute

    job = jobs.create_job(db, institute_id=user.institute_id, owner_id=user.id, job_type="rag_reindex_institution")
    jobs.dispatch(reindex_institute, str(user.institute_id), str(job.id), job=job, db=db)
    return JobOut.model_validate(job).model_dump(mode="json")


@router.get("/knowledge/documents/{doc_id}/download")
def download(doc_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    doc = get_scoped(db, KnowledgeDocument, doc_id, user, label="Document")
    return {"url": presigned_url_for(db, doc.source_file_id, user)}


@router.post("/rag/query", response_model=list[RagHit])
def rag_query(data: RagQueryIn, user: CurrentUser = Depends(require_institution)) -> list[RagHit]:
    """Institution-only retrieval preview; the tenant filter is taken from the authenticated user."""
    from rag.retrieval.retriever import retrieve

    hits = retrieve(institute_id=user.institute_id, query=data.query, role=data.role, topic=data.topic, skill=data.skill,
                    document_type=data.document_type, k=data.k, min_score=0.0)
    return [RagHit(chunk_id=h.chunk_id, text=h.text, score=h.score, doc_id=str(h.metadata.get("doc_id")),
                   source_title=str(h.metadata.get("source_title")), version=int(h.metadata.get("version", 0)),
                   metadata=h.metadata) for h in hits]
