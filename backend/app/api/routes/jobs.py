from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.core.errors import NotFound
from app.models import Job
from app.schemas.common import JobOut
from app.services.tenancy import get_scoped

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> Job:
    job = get_scoped(db, Job, job_id, user, label="Job")
    if user.is_student and job.owner_id != user.id:
        raise NotFound("Job not found")
    return job
