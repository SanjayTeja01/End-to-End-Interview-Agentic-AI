"""Autonomous interview runtime: session start/resume, answer intake (idempotent), turn processing, completion.

The interview advances only through these functions, called from API requests (fast, enqueue only) and Celery
workers (slow: STT, LLM, TTS). No institution observer is required at any point.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.logging import log_event
from app.models import Answer, FileObject, Interview, InterviewCandidate, InterviewSession, Question, User
from app.models.base import utcnow
from app.services import realtime
from app.services.files import AUDIO_MIME, VIDEO_MIME, store_file, validate_upload
from app.services.interviews import evaluate_candidate
from app.services.speech import get_stt
from app.services.tenancy import get_scoped
from storage.minio.client import get_storage
from storage.minio.keys import interview_media_key

log = logging.getLogger(__name__)
ACTIVE_STATES = ("initializing", "in_progress")


def _tasks():  # noqa: ANN202
    from app.workers import media_tasks

    return media_tasks


# ------------------------------------------------------------------ start / resume
def start_or_resume(db: Session, user: CurrentUser, interview_id: uuid.UUID) -> InterviewSession:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    candidate = db.get(User, user.id)
    existing = db.execute(select(InterviewSession).where(InterviewSession.interview_id == iv.id,
                                                         InterviewSession.candidate_id == user.id)).scalar_one_or_none()
    if existing and existing.status in ACTIVE_STATES:
        log_event(log, "interview_resumed", session_id=str(existing.id))
        return existing  # reconnect / browser refresh resumes the same session
    if existing:
        raise Conflict(f"You have already taken this interview (status: {existing.status})")
    # Authoritative backend eligibility check (never trust the client or an LLM for access control)
    res = evaluate_candidate(db, iv, candidate, use_semantic=True)
    if not res.eligible or not res.joinable:
        raise Forbidden(f"Not eligible to join: {res.reason}")
    session = InterviewSession(interview_id=iv.id, candidate_id=user.id, institute_id=user.institute_id,
                               status="initializing", started_at=utcnow(), current_difficulty=iv.initial_difficulty)
    db.add(session)
    db.flush()
    session.state = {"session_id": str(session.id), "started_at": session.started_at.isoformat(), "next_action": "initialize"}
    ic = db.execute(select(InterviewCandidate).where(InterviewCandidate.interview_id == iv.id,
                                                     InterviewCandidate.candidate_id == user.id)).scalar_one_or_none()
    if ic is None:
        ic = InterviewCandidate(interview_id=iv.id, candidate_id=user.id, institute_id=user.institute_id,
                                eligibility_status="eligible", eligibility_reason=res.reason, match_score=res.match_score)
        db.add(ic)
    ic.participation_status = "in_progress"
    db.commit()
    t = _tasks()
    t.start_session.apply_async(args=[str(session.id)])
    _schedule_timer(session.id, iv.duration_minutes * 60 + 15)
    log_event(log, "interview_started", session_id=str(session.id), interview_id=str(iv.id))
    return session


def _schedule_timer(session_id: uuid.UUID, countdown: int) -> None:
    """Server-side duration enforcement (independent of the browser timer). Skipped in eager/test mode."""
    if get_settings().celery_eager:
        return
    _tasks().enforce_duration.apply_async(args=[str(session_id)], countdown=countdown)


def own_session(db: Session, user: CurrentUser, session_id: uuid.UUID) -> InterviewSession:
    s = get_scoped(db, InterviewSession, session_id, user, label="Session")
    if user.is_student and s.candidate_id != user.id:
        raise NotFound("Session not found")
    return s


# ------------------------------------------------------------------ answers
def submit_answer(db: Session, user: CurrentUser, session_id: uuid.UUID, *, question_id: uuid.UUID,
                  idempotency_key: str, audio: bytes | None = None, audio_name: str | None = None,
                  video: bytes | None = None, video_name: str | None = None, transcript: str | None = None,
                  started_at: datetime | None = None, ended_at: datetime | None = None) -> tuple[Answer, bool]:
    s = own_session(db, user, session_id)
    if not user.is_student:
        raise Forbidden("Only the candidate can answer")
    dup = db.execute(select(Answer).where(Answer.idempotency_key == idempotency_key)).scalar_one_or_none()
    if dup:
        if dup.session_id != s.id or dup.candidate_id != user.id:
            raise Conflict("Idempotency key already used")
        return dup, True
    prior = db.execute(select(Answer).where(Answer.question_id == question_id)).scalar_one_or_none()
    if prior:
        return prior, True  # client retried with a new key — never duplicate answers
    if s.status != "in_progress":
        raise Conflict(f"Session is not accepting answers (status: {s.status})")
    if s.current_question_id != question_id:
        raise Conflict("This question is no longer current")
    settings = get_settings()
    iv = db.get(Interview, s.interview_id)
    audio_file = video_file = None
    if audio:
        vf = validate_upload(audio, audio_name, allowed=AUDIO_MIME, max_mb=settings.max_media_upload_mb)
        audio_file = store_file(db, vf, key=interview_media_key(s.institute_id, s.interview_id, s.candidate_id, "audio", vf.ext),
                                owner_id=user.id, institute_id=s.institute_id, file_type="audio")
    if video and iv.record_media:
        vv = validate_upload(video, video_name, allowed=VIDEO_MIME, max_mb=settings.max_media_upload_mb)
        video_file = store_file(db, vv, key=interview_media_key(s.institute_id, s.interview_id, s.candidate_id, "video", vv.ext),
                                owner_id=user.id, institute_id=s.institute_id, file_type="video")
    if not audio_file and not transcript:
        raise Conflict("An audio answer or transcript is required")
    a = Answer(question_id=question_id, session_id=s.id, candidate_id=user.id, institute_id=s.institute_id,
               transcript=transcript, started_at=started_at, ended_at=ended_at,
               duration_seconds=(ended_at - started_at).total_seconds() if started_at and ended_at else None,
               audio_file_id=audio_file.id if audio_file else None, video_file_id=video_file.id if video_file else None,
               status="transcribed" if transcript else "received", idempotency_key=idempotency_key,
               # A browser speech-recognition transcript sent with the audio skips server STT entirely (the audio is
               # still stored); without one the worker transcribes the audio with faster-whisper.
               meta={"input": ("audio+browser_transcript" if transcript else "audio") if audio_file else "text_fallback"})
    db.add(a)
    db.flush()
    mark_turn(db, a, "answer_finalized", input=a.meta["input"])
    db.commit()
    realtime.publish(s.id, "answer_received", {"question_id": str(question_id), "input": a.meta["input"]})
    log_event(log, "answer_received", session_id=str(s.id), question_id=str(question_id), input=a.meta["input"])
    _tasks().process_answer.apply_async(args=[str(a.id)])
    return a, False


# ------------------------------------------------------------------ worker-side turn processing
def _lock_session(db: Session, session_id: uuid.UUID, *, nowait: bool = False) -> InterviewSession:
    return db.execute(select(InterviewSession).where(InterviewSession.id == session_id)
                      .with_for_update(nowait=nowait)).scalar_one()


def _save_state(session: InterviewSession, state: dict) -> None:
    session.state = json.loads(json.dumps(state, default=str))  # guarantees JSON-serialisable snapshot
    session.lock_version += 1


def _after_complete(new_state: dict) -> None:
    if new_state.get("report_id"):
        from app.workers.report_tasks import export_report_pdf

        export_report_pdf.apply_async(args=[new_state["report_id"]])


def run_initialize(db: Session, session_id: uuid.UUID) -> None:
    from app.graph.workflow import run

    s = _lock_session(db, session_id)
    if s.status != "initializing":
        db.rollback()
        return
    state = dict(s.state or {})
    state["next_action"] = "initialize"
    try:
        new_state = run(db, state)
    except Exception:
        db.rollback()
        s = _lock_session(db, session_id)
        s.status = "failed"
        s.termination_reason = "initialization_failed"
        db.commit()
        realtime.publish(session_id, "error", {"message": "The interview could not be started. Please contact your institution."})
        raise
    new_state.pop("turn_marks", None)
    event = new_state.pop("question_event", None)
    _save_state(s, new_state)
    s.status = "completed" if new_state.get("next_action") == "done" else "in_progress"
    db.commit()
    if event:
        realtime.publish(session_id, "question", event)
    realtime.publish(session_id, "session_state", {"status": s.status})


PENDING_ANSWER_STATES = ("received", "transcribing", "transcribed", "evaluating")


def mark_turn(db: Session, answer: Answer, step: str, **extra) -> None:  # noqa: ANN003
    """Record when a turn step happened (answer.meta.timeline) and log it, so the execution order is provable."""
    now = time.time()
    meta = dict(answer.meta or {})
    meta["timeline"] = {**meta.get("timeline", {}), step: now}
    answer.meta = meta
    log_event(log, "turn_step", step=step, session_id=str(answer.session_id), question_id=str(answer.question_id),
              answer_id=str(answer.id), at=datetime.fromtimestamp(now, timezone.utc).isoformat(), **extra)


def _merge_marks(db: Session, answer: Answer, marks: dict | None) -> None:
    for step, ts in sorted((marks or {}).items(), key=lambda kv: kv[1]):
        meta = dict(answer.meta or {})
        meta["timeline"] = {**meta.get("timeline", {}), step: ts}
        answer.meta = meta
        log_event(log, "turn_step", step=step, session_id=str(answer.session_id), question_id=str(answer.question_id),
                  answer_id=str(answer.id), at=datetime.fromtimestamp(ts, timezone.utc).isoformat())


def publish_turn(answer: Answer, phase: str, **extra) -> None:  # noqa: ANN003
    """Tell the candidate's screen what the server is doing with their answer right now."""
    realtime.publish(answer.session_id, "turn_status", {"answer_id": str(answer.id), "question_id": str(answer.question_id),
                                                        "phase": phase, **extra})


def transcribe_answer(db: Session, answer: Answer) -> str:
    if answer.transcript is not None:
        return answer.transcript
    f = db.get(FileObject, answer.audio_file_id)
    answer.status = "transcribing"
    mark_turn(db, answer, "transcription_started")
    db.commit()
    publish_turn(answer, "transcribing")
    from app.services.speech import SpeechError, call_with_timeout

    audio = get_storage().get_bytes(f.object_key)
    try:
        tr = call_with_timeout(lambda: get_stt().transcribe(audio, f.object_key.rsplit(".", 1)[-1]),
                               get_settings().stt_timeout_seconds, "transcription")
    except SpeechError:
        raise
    except Exception as exc:  # noqa: BLE001 — e.g. the speech model could not be loaded or downloaded
        raise SpeechError(f"Speech-to-text unavailable: {type(exc).__name__}") from exc
    answer.transcript = tr.text
    answer.status = "transcribed"
    answer.meta = {**(answer.meta or {}), "stt_language": tr.language, "stt_duration": tr.duration_seconds,
                   "stt_avg_logprob": tr.avg_logprob}
    mark_turn(db, answer, "transcription_completed")
    db.commit()
    realtime.publish(answer.session_id, "transcript", {"question_id": str(answer.question_id), "text": tr.text})
    return tr.text


def _drop_stale(db: Session, a: Answer, s: InterviewSession) -> bool:
    current = ((s.state or {}).get("current_question") or {}).get("id")
    if current == str(a.question_id) and s.status == "in_progress":
        return False
    db.rollback()
    if s.status == "in_progress":  # answer to a question that is no longer current: never evaluate it
        a = db.get(Answer, a.id)
        a.status, a.error = "failed", "stale_answer"
        db.commit()
    return True


def run_process_answer(db: Session, answer_id: uuid.UUID) -> None:
    """One interview turn, in strict order, each stage committed before the next starts:

        answer finalised -> (transcribed) -> evaluated -> performance profile updated -> next question decided
        -> next question generated -> next question presented

    Stage 1 (evaluation + profile) and stage 2 (adaptive decision + next question) are separate transactions, so a
    retry after a failure in stage 2 re-uses the stored evaluation instead of scoring the answer again, and the
    next question can only ever be chosen from an evaluation that is already committed.
    """
    from app.graph.workflow import run

    a = db.get(Answer, answer_id)
    if a is None or a.status in ("failed", "evaluation_failed"):
        return  # dropped (interview ended / stale) or waiting for the candidate to ask for a retry
    if a.status in ("received", "transcribing"):
        transcribe_answer(db, a)

    # ---- stage 1: evaluate the answer and update the performance profile
    if a.status != "evaluated":
        s = _lock_session(db, a.session_id)
        if _drop_stale(db, a, s):
            return
        a.status = "evaluating"
        a.meta = {**(a.meta or {}), "eval_attempts": int((a.meta or {}).get("eval_attempts", 0)) + 1}
        mark_turn(db, a, "evaluation_started", attempt=a.meta["eval_attempts"])
        db.commit()  # visible to /state and the monitor while the LLM works
        publish_turn(a, "evaluating", attempt=a.meta["eval_attempts"])

        s = _lock_session(db, a.session_id)
        db.refresh(a)
        if a.status != "evaluating" or _drop_stale(db, a, s):
            db.rollback()
            return  # ended meanwhile, or another worker finished it
        state = dict(s.state or {})
        state.update(next_action="process_answer", evaluate_only=True, turn_marks={},
                     candidate_answer={"answer_id": str(a.id), "question_id": str(a.question_id), "transcript": a.transcript})
        new_state = run(db, state)
        marks = new_state.pop("turn_marks", {})
        new_state.pop("evaluate_only", None)
        _save_state(s, new_state)
        a.status = "evaluated"
        a.error = None
        _merge_marks(db, a, marks)
        db.commit()
        ev = new_state.get("evaluation") or {}
        publish_turn(a, "choosing_next", score=ev.get("overall_score"), band=ev.get("band"))

    # ---- stage 2: choose and ask the next question from the evaluation stored above
    s = _lock_session(db, a.session_id)
    db.refresh(a)
    if s.status != "in_progress" or s.current_question_id != a.question_id:
        db.rollback()
        return  # interview ended, or this turn already moved on (duplicate task)
    state = dict(s.state or {})
    if (state.get("evaluation") or {}).get("question_id") != str(a.question_id):
        raise RuntimeError("stored evaluation does not belong to the current answer")  # never adapt on stale data
    started = time.monotonic()
    state.update(next_action="next_question", turn_marks={}, question_event=None)
    new_state = run(db, state)
    marks = new_state.pop("turn_marks", {})
    event = new_state.pop("question_event", None)
    _save_state(s, new_state)
    if new_state.get("next_action") == "done":
        s.status = "completed"
    _merge_marks(db, a, marks)
    db.commit()
    if event:
        realtime.publish(s.id, "question", event)
        mark_turn(db, a, "next_question_presented", next_sequence=event["question"]["sequence"])
        db.commit()
    log_event(log, "answer_processed", session_id=str(s.id), answer_id=str(answer_id),
              next_question_ms=int((time.monotonic() - started) * 1000),
              turn_ms=int(1000 * (time.time() - (a.meta or {}).get("timeline", {}).get("answer_finalized", time.time()))))
    realtime.publish(s.id, "session_state", {"status": s.status, "progress": s.progress})
    if s.status == "completed":
        _after_complete(new_state)


def record_turn_failure(db: Session, answer_id: uuid.UUID, exc: BaseException, *, final: bool) -> None:
    """A turn step failed. Keep the answer and say so; never fabricate a score or skip the evaluation.

    final=False: a retry is scheduled (answer goes back to 'transcribed').
    final=True:  attempts are used up; the answer becomes 'evaluation_failed' and the candidate can retry it.
    An answer that was already evaluated keeps its evaluation; only the next-question step is retried.
    """
    db.rollback()
    a = db.get(Answer, answer_id)
    if a is None or a.status == "failed":
        return
    detail = f"{type(exc).__name__}: {str(exc)[:300]}"
    a.meta = {**(a.meta or {}), "last_error": detail}
    if a.status != "evaluated":
        a.status = "evaluation_failed" if final else "transcribed" if a.transcript is not None else "received"
        a.error = detail if final else None
    mark_turn(db, a, "turn_failed" if final else "turn_retry_scheduled", error=detail)
    db.commit()
    if final and a.status == "evaluation_failed":
        publish_turn(a, "evaluation_failed", retry_allowed=True,
                     message="We couldn't evaluate your answer just now. Your answer is saved. Press Retry to try "
                             "again; the next question waits for this evaluation.")
    else:
        publish_turn(a, "retrying", message="Still working on your answer…")


def retry_answer(db: Session, user: CurrentUser, session_id: uuid.UUID, answer_id: uuid.UUID) -> Answer:
    """Candidate asks to retry an answer whose evaluation failed."""
    s = own_session(db, user, session_id)
    a = db.get(Answer, answer_id)
    if a is None or a.session_id != s.id:
        raise NotFound("Answer not found")
    if s.status != "in_progress" or a.status != "evaluation_failed":
        return a  # nothing to retry (already moving, finished, or the interview ended)
    a.status = "transcribed" if a.transcript is not None else "received"
    a.error = None
    a.meta = {**(a.meta or {}), "manual_retries": int((a.meta or {}).get("manual_retries", 0)) + 1}
    mark_turn(db, a, "retry_requested")
    db.commit()
    _tasks().process_answer.apply_async(args=[str(a.id)])
    publish_turn(a, "evaluating")
    return a


def request_completion(db: Session, session_id: uuid.UUID, reason: str, *, by_institution: bool = False,
                       wait: bool = True) -> None:
    """Candidate ends early, institution terminates, or time runs out.

    Ending never waits for an in-flight answer: an answer that is not evaluated yet is dropped (its recording is
    kept) and the report is built from the answers already evaluated. With wait=False (HTTP requests), if a worker
    is mid-evaluation and holds the session lock, the end request is handed to a worker instead of blocking.
    """
    try:
        s = _lock_session(db, session_id, nowait=not wait)
    except OperationalError:
        db.rollback()
        _tasks().complete_session.apply_async(args=[str(session_id), reason, by_institution])
        return
    if s.status not in ACTIVE_STATES:
        db.rollback()
        return
    state = dict(s.state or {})
    state["candidate_ended" if not by_institution else "terminated"] = True
    state["stop_reason"] = reason
    pending = db.execute(select(Answer).where(Answer.session_id == s.id,
                                              Answer.status.in_(PENDING_ANSWER_STATES))).scalars().all()
    for a in pending:
        a.status = "failed"
        a.error = "interview_ended"
    _save_state(s, state)
    s.status = "finalizing"
    db.commit()
    _tasks().finalize_session.apply_async(args=[str(s.id)])


def run_finalize(db: Session, session_id: uuid.UUID) -> None:
    from app.graph.workflow import run

    s = _lock_session(db, session_id)
    if s.status == "completed":
        db.rollback()
        return
    state = dict(s.state or {})
    if not state.get("plan"):
        # Ended before the first question was generated: load context so a (minimal) report can be produced.
        from app.graph.context import load_context

        state.update(load_context(db, s.id))
        state.setdefault("evaluations", [])
    _score_leftover_answers(db, s, state)
    state["next_action"] = "finalize"
    new_state = run(db, state)
    _save_state(s, new_state)
    s.status = "completed"
    db.commit()
    realtime.publish(s.id, "session_state", {"status": s.status, "progress": 1.0})
    _after_complete(new_state)


def _score_leftover_answers(db: Session, s: InterviewSession, state: dict) -> None:
    """Answers that were finalised but not evaluated when the interview ended (typically the last answer, still in
    progress when time ran out). No next question depends on them, so each is evaluated once here and the report
    covers every answer the candidate gave. If that evaluation fails the answer is reported as not scored; it is
    never given an assumed score. Already-evaluated answers are never re-evaluated."""
    from app.graph.workflow import RunnableConfigFor, evaluate_node
    from app.models import Evaluation
    from app.services.llm import LLMError

    if not state.get("interview_config"):
        return
    scored = {e.get("question_id") for e in state.get("evaluations", [])}
    rows = db.execute(select(Answer, Question).join(Question, Question.id == Answer.question_id)
                      .outerjoin(Evaluation, Evaluation.answer_id == Answer.id)
                      .where(Answer.session_id == s.id, Answer.transcript.is_not(None), Evaluation.id.is_(None))
                      .order_by(Question.sequence)).all()
    for a, q in rows:
        if str(q.id) in scored or a.error == "stale_answer":
            continue
        qd = {"id": str(q.id), "sequence": q.sequence, "text": q.text, "topic": q.topic, "skill": q.skill,
              "difficulty": q.difficulty, "question_type": q.question_type,
              "category": (q.context_meta or {}).get("category"),
              "expected_points": (q.context_meta or {}).get("expected_points", [])}
        try:
            out = evaluate_node({**state, "current_question": qd, "candidate_answer": {
                "answer_id": str(a.id), "question_id": str(q.id), "transcript": a.transcript}}, RunnableConfigFor(db))
        except LLMError as exc:
            a.meta = {**(a.meta or {}), "final_evaluation_error": str(exc)[:300]}
            log_event(log, "leftover_answer_not_scored", session_id=str(s.id), answer_id=str(a.id))
            continue
        for k in ("evaluations", "topic_stats", "weak_topics", "strong_topics", "performance", "transcript"):
            state[k] = out[k]
        a.status, a.error = "evaluated", None
        mark_turn(db, a, "evaluated_at_finalize")
        log_event(log, "leftover_answer_scored", session_id=str(s.id), answer_id=str(a.id),
                  score=out["evaluation"]["overall_score"])


def time_is_up(db: Session, s: InterviewSession) -> bool:
    if not s.started_at:
        return False
    started = s.started_at if s.started_at.tzinfo else s.started_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds() >= db.get(Interview, s.interview_id).duration_minutes * 60


_time_up_requested: dict[uuid.UUID, float] = {}


def sweep_overdue_sessions(db: Session, *, grace_seconds: int = 5) -> list[uuid.UUID]:
    """End every active session whose time is up. Runs every few seconds inside the API process, so the interview
    ends on time even if the Celery countdown task is delayed or lost or the browser tab is closed."""
    now = datetime.now(timezone.utc)
    rows = db.execute(select(InterviewSession.id, InterviewSession.started_at, Interview.duration_minutes)
                      .join(Interview, Interview.id == InterviewSession.interview_id)
                      .where(InterviewSession.status.in_(ACTIVE_STATES))).all()
    db.rollback()  # release the read snapshot before taking row locks
    ended = []
    for session_id, started_at, minutes in rows:
        if started_at is None:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if (now - started_at).total_seconds() >= minutes * 60 + grace_seconds:
            if time.monotonic() - _time_up_requested.get(session_id, -1e9) < 60:
                continue  # already handed to a worker that is waiting for the session lock
            _time_up_requested[session_id] = time.monotonic()
            request_completion(db, session_id, "duration_reached", by_institution=True, wait=False)
            log_event(log, "interview_time_up", session_id=str(session_id))
            ended.append(session_id)
    _redispatch_stuck_answers(db)
    return ended


_MAX_REDISPATCH = 2


def _redispatch_stuck_answers(db: Session) -> None:
    """A turn whose task died or was lost (worker restart, crash) would leave the candidate on "Evaluating…"
    forever. A turn with no progress for TURN_STUCK_SECONDS is re-queued (at most twice). Every stage is
    idempotent, so a re-queued turn resumes where it stopped: an evaluated answer is not scored again."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=get_settings().turn_stuck_seconds)
    unfinished = (Answer.status.in_(PENDING_ANSWER_STATES)
                  | ((Answer.status == "evaluated") & (InterviewSession.current_question_id == Answer.question_id)))
    stuck = db.execute(select(Answer).join(InterviewSession, InterviewSession.id == Answer.session_id)
                       .where(InterviewSession.status == "in_progress", unfinished,
                              Answer.updated_at < cutoff)).scalars().all()
    for a in stuck:
        n = int((a.meta or {}).get("redispatched", 0))
        if n >= _MAX_REDISPATCH:
            continue
        a.meta = {**(a.meta or {}), "redispatched": n + 1}
        mark_turn(db, a, "turn_redispatched", status=a.status)
        db.commit()
        _tasks().process_answer.apply_async(args=[str(a.id)])
    db.rollback()


def run_enforce_duration(db: Session, session_id: uuid.UUID) -> None:
    s = db.get(InterviewSession, session_id)
    if s is None or s.status not in ACTIVE_STATES:
        return
    iv = db.get(Interview, s.interview_id)
    elapsed = (datetime.now(timezone.utc) - s.started_at).total_seconds() if s.started_at else 0
    if elapsed >= iv.duration_minutes * 60:
        request_completion(db, s.id, "duration_reached", by_institution=True)
    else:
        _schedule_timer(s.id, int(iv.duration_minutes * 60 - elapsed) + 5)


# ------------------------------------------------------------------ read models
def session_state(db: Session, s: InterviewSession, *, include_tts_url: bool = True) -> dict:
    iv = db.get(Interview, s.interview_id)
    q = db.get(Question, s.current_question_id) if s.current_question_id else None
    answered = q is not None and db.execute(select(Answer.id).where(Answer.question_id == q.id)).first() is not None
    qout = None
    if q:
        url = None
        if q.tts_file_id and include_tts_url:
            f = db.get(FileObject, q.tts_file_id)
            url = get_storage().presigned_get(f.object_key, expires_seconds=get_settings().presigned_url_expiry_seconds)
        qout = {"id": q.id, "sequence": q.sequence, "text": q.text, "spoken_text": q.spoken_text, "topic": q.topic,
                "difficulty": q.difficulty, "question_type": q.question_type, "tts_url": url}
    turn = None
    if q is not None:
        a = db.execute(select(Answer).where(Answer.question_id == q.id)).scalar_one_or_none()
        if a is not None:
            phase = {"received": "transcribing", "transcribing": "transcribing", "transcribed": "evaluating",
                     "evaluating": "evaluating", "evaluated": "choosing_next", "evaluation_failed": "evaluation_failed",
                     "failed": "failed"}.get(a.status, a.status)
            turn = {"answer_id": a.id, "status": a.status, "phase": phase,
                    "attempts": int((a.meta or {}).get("eval_attempts", 0)),
                    "retry_allowed": a.status == "evaluation_failed" and s.status == "in_progress",
                    "error": a.error if a.status == "evaluation_failed" else None}
    awaiting = "none"
    if s.status == "in_progress":
        awaiting = "processing" if answered else "answer"
    elif s.status in ("initializing", "finalizing"):
        awaiting = "processing"
    elapsed = (datetime.now(timezone.utc) - s.started_at).total_seconds() if s.started_at else 0.0
    if s.ended_at and s.started_at:
        elapsed = (s.ended_at - s.started_at).total_seconds()
    return {"session_id": s.id, "interview_id": s.interview_id, "status": s.status, "question_index": s.question_index,
            "question_count": iv.question_count, "progress": s.progress, "current_topic": s.current_topic,
            "current_difficulty": s.current_difficulty, "started_at": s.started_at, "duration_minutes": iv.duration_minutes,
            "elapsed_seconds": round(elapsed, 1), "current_question": qout, "awaiting": awaiting, "turn": turn,
            "ice_servers": get_settings().ice_server_list, "record_media": iv.record_media}
