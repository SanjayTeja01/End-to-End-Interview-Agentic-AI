"""Live interview runtime endpoints (`{session_id}` identifies the candidate's interview session)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_student
from app.core.database import get_db
from app.schemas.runtime import AnswerAccepted, CompleteIn, SessionStateOut, TextAnswerIn
from app.services import runtime

router = APIRouter(prefix="/interview", tags=["interview-runtime"])


@router.get("/{session_id}/state", response_model=SessionStateOut)
def state(session_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Used on (re)connect for session recovery."""
    return runtime.session_state(db, runtime.own_session(db, user, session_id))


@router.post("/{session_id}/answer", response_model=AnswerAccepted, status_code=202)
async def answer_audio(session_id: uuid.UUID, question_id: uuid.UUID = Form(...), idempotency_key: str = Form(..., min_length=8, max_length=80),
                       started_at: datetime | None = Form(default=None), ended_at: datetime | None = Form(default=None),
                       transcript: str | None = Form(default=None, max_length=20000),
                       audio: UploadFile = File(...), video: UploadFile | None = File(default=None),
                       user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> AnswerAccepted:
    audio_bytes = await audio.read()
    video_bytes = await video.read() if video else None
    a, dup = runtime.submit_answer(db, user, session_id, question_id=question_id, idempotency_key=idempotency_key,
                                   audio=audio_bytes, audio_name=audio.filename, video=video_bytes,
                                   video_name=video.filename if video else None, started_at=started_at, ended_at=ended_at,
                                   transcript=(transcript or "").strip() or None)
    return AnswerAccepted(answer_id=a.id, status=a.status, duplicate=dup)


@router.post("/{session_id}/answer/text", response_model=AnswerAccepted, status_code=202)
def answer_text(session_id: uuid.UUID, data: TextAnswerIn, user: CurrentUser = Depends(require_student),
                db: Session = Depends(get_db)) -> AnswerAccepted:
    a, dup = runtime.submit_answer(db, user, session_id, question_id=data.question_id, idempotency_key=data.idempotency_key,
                                   transcript=data.transcript, started_at=data.started_at, ended_at=data.ended_at)
    return AnswerAccepted(answer_id=a.id, status=a.status, duplicate=dup)


@router.post("/{session_id}/answer/{answer_id}/retry", response_model=AnswerAccepted, status_code=202)
def retry_answer(session_id: uuid.UUID, answer_id: uuid.UUID, user: CurrentUser = Depends(require_student),
                 db: Session = Depends(get_db)) -> AnswerAccepted:
    """Re-run an answer whose evaluation failed (the saved answer is evaluated again; nothing is re-recorded)."""
    a = runtime.retry_answer(db, user, session_id, answer_id)
    return AnswerAccepted(answer_id=a.id, status=a.status, duplicate=False)


@router.post("/{session_id}/complete", status_code=202)
def complete(session_id: uuid.UUID, data: CompleteIn | None = None, user: CurrentUser = Depends(require_student),
             db: Session = Depends(get_db)) -> dict:
    s = runtime.own_session(db, user, session_id)
    reason = "duration_reached" if runtime.time_is_up(db, s) else "ended_by_candidate"
    runtime.request_completion(db, s.id, reason, wait=False)
    return {"session_id": str(s.id), "status": "finalizing"}
