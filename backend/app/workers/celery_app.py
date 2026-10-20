"""Celery application. Redis is the broker/result backend (transient infrastructure, not a database)."""
from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery("interview_agent", broker=settings.redis_url, backend=settings.redis_url,
                    include=["app.workers.resume_tasks", "app.workers.rag_tasks", "app.workers.media_tasks",
                             "app.workers.report_tasks", "app.workers.interview_tasks"])
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC", enable_utc=True,
    task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    task_time_limit=600, task_soft_time_limit=540, result_expires=3600,
    # Recycle worker processes now and then so a speech call abandoned after its timeout cannot pile up.
    worker_max_tasks_per_child=50,
    task_default_queue="default",
    task_routes={
        "app.workers.media_tasks.*": {"queue": "media"},
        "app.workers.rag_tasks.*": {"queue": "rag"},
        "app.workers.report_tasks.*": {"queue": "reports"},
    },
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
    broker_connection_retry_on_startup=True,
)


@worker_process_init.connect
def _init_worker(**_kwargs) -> None:  # noqa: ANN003
    configure_logging(settings.log_level)
    settings.require_secrets()
