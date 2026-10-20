from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_institution
from app.core.database import get_db
from app.core.logging import log_event
from app.models import Interview, InterviewSession, User
from app.services import analytics, runtime
from app.services.tenancy import get_scoped

import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/interviews/{interview_id}")
def interview_sessions(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> list[dict]:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    rows = db.execute(select(InterviewSession, User).join(User, User.id == InterviewSession.candidate_id)
                      .where(InterviewSession.interview_id == iv.id, InterviewSession.institute_id == user.institute_id)
                      .order_by(InterviewSession.started_at.desc())).all()
    return [{"session_id": str(s.id), "candidate_id": str(u.id), "candidate": u.full_name, "status": s.status,
             "question_index": s.question_index, "question_count": iv.question_count, "progress": s.progress,
             "current_topic": s.current_topic, "current_difficulty": s.current_difficulty,
             "started_at": s.started_at.isoformat() if s.started_at else None, "connection": s.connection} for s, u in rows]


@router.get("/sessions/{session_id}")
def session_detail(session_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    s = get_scoped(db, InterviewSession, session_id, user, label="Session")
    cand = db.get(User, s.candidate_id)
    return {"candidate": {"id": str(cand.id), "full_name": cand.full_name},
            "state": runtime.session_state(db, s, include_tts_url=False), **analytics.live_session_snapshot(db, s)}


@router.post("/sessions/{session_id}/terminate", status_code=202)
def terminate(session_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    s = get_scoped(db, InterviewSession, session_id, user, label="Session")
    log_event(log, "interview_terminated_by_institution", session_id=str(s.id), by=str(user.id))
    runtime.request_completion(db, s.id, "terminated_by_institution", by_institution=True, wait=False)
    return {"session_id": str(s.id), "status": "finalizing"}
