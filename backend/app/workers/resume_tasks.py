from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.services import jobs, resumes
from app.services.llm import LLMConfigError
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=1, default_retry_delay=5)
def process_resume(self, resume_id: str, job_id: str | None = None) -> None:  # noqa: ANN001
    db = SessionLocal()
    try:
        jobs.mark(db, job_id, "processing")
        resumes.process(db, uuid.UUID(resume_id))
        jobs.mark(db, job_id, "completed", result={"resume_id": resume_id})
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries and "LLM" in type(exc).__name__ \
                and not isinstance(exc, LLMConfigError):
            raise self.retry(exc=exc)
        jobs.mark(db, job_id, "failed", error=str(exc))
        raise
    finally:
        db.close()
