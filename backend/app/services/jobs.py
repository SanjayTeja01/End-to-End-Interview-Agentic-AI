"""Async job bookkeeping + dispatch to Celery (eager in tests)."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models import Job

log = logging.getLogger(__name__)


def create_job(db: Session, *, institute_id: uuid.UUID, owner_id: uuid.UUID | None, job_type: str,
               entity_type: str | None = None, entity_id: uuid.UUID | None = None) -> Job:
    job = Job(institute_id=institute_id, owner_id=owner_id, job_type=job_type, entity_type=entity_type,
              entity_id=entity_id, status="pending")
    db.add(job)
    db.flush()
    return job


def dispatch(task, *args, countdown: int | None = None, job: Job | None = None, db: Session | None = None) -> None:  # noqa: ANN001
    """Commit first so the worker can see the rows, then enqueue."""
    if db is not None:
        db.commit()
    res = task.apply_async(args=args, countdown=countdown)
    if job is not None and db is not None:
        job.celery_task_id = getattr(res, "id", None)
        db.commit()
        db.refresh(job)  # pick up status written by the worker (or eager execution)


def mark(db: Session, job_id: uuid.UUID | str | None, status: str, *, error: str | None = None, result: dict | None = None) -> None:
    if not job_id:
        return
    job = db.get(Job, uuid.UUID(str(job_id)))
    if job is None:
        return
    job.status = status
    if error:
        job.error = error[:2000]
    if result is not None:
        job.result = result
    db.commit()
    log_event(log, f"worker_job_{status}", job_id=str(job.id), job_type=job.job_type)
