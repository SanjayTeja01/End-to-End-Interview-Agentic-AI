from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_student
from app.core.database import get_db
from app.core.errors import NotFound
from app.models import Resume
from app.schemas.common import JobOut
from app.schemas.profile import ResumeAnalysisOut, ResumeOut
from app.services import jobs, resumes
from app.services.files import presigned_url_for
from app.services.tenancy import ensure_own_candidate, get_scoped

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/upload", response_model=dict, status_code=202)
async def upload_resume(file: UploadFile = File(...), user: CurrentUser = Depends(require_student),
                        db: Session = Depends(get_db)) -> dict:
    from app.workers.resume_tasks import process_resume

    data = await file.read()
    r = resumes.upload(db, user, data, file.filename)
    job = jobs.create_job(db, institute_id=user.institute_id, owner_id=user.id, job_type="resume_processing",
                          entity_type="resume", entity_id=r.id)
    db.commit()
    jobs.dispatch(process_resume, str(r.id), str(job.id), job=job, db=db)
    return {"resume": ResumeOut.model_validate(r).model_dump(mode="json"), "job": JobOut.model_validate(job).model_dump(mode="json")}


@router.get("", response_model=list[ResumeOut])
def list_my_resumes(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> list[Resume]:
    return list(db.execute(select(Resume).where(Resume.candidate_id == user.id).order_by(Resume.version.desc())).scalars())


def _get(db: Session, user: CurrentUser, resume_id: uuid.UUID) -> Resume:
    r = get_scoped(db, Resume, resume_id, user, label="Resume")
    ensure_own_candidate(user, r.candidate_id)
    return r


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> Resume:
    return _get(db, user, resume_id)


@router.get("/{resume_id}/analysis", response_model=ResumeAnalysisOut)
def get_analysis(resume_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> Resume:
    return _get(db, user, resume_id)


@router.get("/{resume_id}/download")
def download(resume_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    r = _get(db, user, resume_id)
    if r is None:
        raise NotFound("Resume not found")
    return {"url": presigned_url_for(db, r.file_id, user, candidate_id=r.candidate_id)}
