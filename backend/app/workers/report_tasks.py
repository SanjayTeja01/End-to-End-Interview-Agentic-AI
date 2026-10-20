from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.models import Report
from app.services.reports import export_report
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=15)
def export_report_pdf(self, report_id: str) -> None:  # noqa: ANN001
    db = SessionLocal()
    try:
        export_report(db, uuid.UUID(report_id))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        r = db.get(Report, uuid.UUID(report_id))
        if r:
            r.export_status = "failed"
            db.commit()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        db.close()
