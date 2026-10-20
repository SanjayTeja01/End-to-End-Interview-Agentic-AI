from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.services import jobs
from app.workers.celery_app import celery_app
from rag.ingestion.pipeline import ingest_version
from rag.reindexing.reindex import reindex_all


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def index_document_version(self, version_id: str, job_id: str | None = None) -> None:  # noqa: ANN001
    db = SessionLocal()
    try:
        jobs.mark(db, job_id, "processing")
        chunks = ingest_version(db, uuid.UUID(version_id))
        jobs.mark(db, job_id, "completed", result={"chunks": chunks})
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        jobs.mark(db, job_id, "failed", error=str(exc))
        raise
    finally:
        db.close()


@celery_app.task
def reindex_institute(institute_id: str | None = None, job_id: str | None = None, only_stale: bool = False) -> dict:
    db = SessionLocal()
    try:
        jobs.mark(db, job_id, "processing")
        summary = reindex_all(db, institute_id=uuid.UUID(institute_id) if institute_id else None, reset=bool(institute_id),
                              only_stale=only_stale)
        jobs.mark(db, job_id, "completed", result=summary)
        return summary
    except Exception as exc:  # noqa: BLE001
        jobs.mark(db, job_id, "failed", error=str(exc))
        raise
    finally:
        db.close()
