"""Interview runtime tasks: start, per-answer processing (STT → evaluation → next question/TTS), completion."""
from __future__ import annotations

import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Answer
from app.services import realtime, runtime
from app.services.llm import LLMConfigError, LLMError
from app.services.speech import SpeechError
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=2)
def start_session(self, session_id: str) -> None:  # noqa: ANN001
    db = SessionLocal()
    try:
        runtime.run_initialize(db, uuid.UUID(session_id))
    except LLMError as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        db.close()


def _retry(task, exc: Exception, *, countdown: int) -> None:  # noqa: ANN001
    if task.request.is_eager:  # tests / single-process dev: run the next attempt inline
        task.apply(args=task.request.args, kwargs=task.request.kwargs, retries=task.request.retries + 1)
        return
    raise task.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, max_retries=None, acks_late=True, soft_time_limit=300, time_limit=330)
def process_answer(self, answer_id: str, provisional_ok: bool = False) -> None:  # noqa: ANN001, ARG001
    """One interview turn: (STT) -> evaluation -> profile update -> adaptive decision -> next question.

    Bounded retries (TURN_EVAL_ATTEMPTS). When they are used up the answer is marked evaluation_failed and the
    candidate is told and offered a retry; the interview never moves on with an invented score. Every failure is
    recorded on the answer and logged; nothing leaves the candidate on "Evaluating…" without an explanation.
    (provisional_ok is accepted only so tasks queued by an older version still run.)
    """
    db = SessionLocal()
    aid = uuid.UUID(answer_id)
    attempts = max(1, get_settings().turn_eval_attempts)
    final = self.request.retries + 1 >= attempts
    try:
        runtime.run_process_answer(db, aid)
    except SpeechError as exc:
        # No retry: transcription already had its full time limit, and a second wait would cost the candidate
        # minutes. Ask them to answer again (or type) straight away instead.
        db.rollback()
        log.warning("turn_speech_error", extra={"data": {"answer_id": answer_id, "error": str(exc)[:300]}})
        a = db.get(Answer, aid)
        if a:
            # The audio stays in MinIO (file row kept); the candidate is asked to answer this question again.
            realtime.publish(a.session_id, "error", {"message": "We could not transcribe your answer. Please answer again "
                                                                "or type your answer.", "question_id": str(a.question_id),
                                                     "retry_allowed": True})
            db.delete(a)
            db.commit()
    except LLMConfigError as exc:
        log.exception("turn_llm_config_error", extra={"data": {"answer_id": answer_id}})
        runtime.record_turn_failure(db, aid, exc, final=True)  # wrong key/model: retrying cannot help
    except (LLMError, SoftTimeLimitExceeded, OperationalError) as exc:
        log.warning("turn_attempt_failed", extra={"data": {"answer_id": answer_id, "attempt": self.request.retries + 1,
                                                           "of": attempts, "error": type(exc).__name__}})
        runtime.record_turn_failure(db, aid, exc, final=final)
        if not final:
            _retry(self, exc, countdown=2 * (self.request.retries + 1))
    except Exception as exc:  # noqa: BLE001 — unexpected bug: record it on the answer instead of failing silently
        log.exception("turn_failed", extra={"data": {"answer_id": answer_id}})
        runtime.record_turn_failure(db, aid, exc, final=True)
        raise
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def finalize_session(self, session_id: str) -> None:  # noqa: ANN001
    db = SessionLocal()
    try:
        runtime.run_finalize(db, uuid.UUID(session_id))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        db.close()


@celery_app.task
def complete_session(session_id: str, reason: str, by_institution: bool = False) -> None:
    """End request that arrived while a worker held the session lock; waits for the lock here instead."""
    db = SessionLocal()
    try:
        runtime.request_completion(db, uuid.UUID(session_id), reason, by_institution=by_institution)
    finally:
        db.close()


@celery_app.task
def enforce_duration(session_id: str) -> None:
    db = SessionLocal()
    try:
        runtime.run_enforce_duration(db, uuid.UUID(session_id))
    finally:
        db.close()
