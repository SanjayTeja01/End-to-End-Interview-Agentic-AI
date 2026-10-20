from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.core.errors import NotFound
from app.models import InterviewRecommendation, Performance, Readiness, Report
from app.schemas.results import ReportOut, ResultOut
from app.services import runtime
from app.services.files import presigned_url_for
from app.services.reports import session_questions

router = APIRouter(prefix="/interview", tags=["results"])


def _latest_report(db: Session, session_id: uuid.UUID) -> Report | None:
    return db.execute(select(Report).where(Report.session_id == session_id).order_by(Report.version.desc())).scalars().first()


@router.get("/{session_id}/result", response_model=ResultOut)
def result(session_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    s = runtime.own_session(db, user, session_id)
    perf = db.execute(select(Performance).where(Performance.session_id == s.id)).scalar_one_or_none()
    ready = db.execute(select(Readiness).where(Readiness.session_id == s.id)).scalar_one_or_none()
    recs = db.execute(select(InterviewRecommendation).where(InterviewRecommendation.session_id == s.id)
                      .order_by(InterviewRecommendation.priority.desc())).scalars().all()
    rep = _latest_report(db, s.id)
    return {
        "session_id": s.id, "interview_id": s.interview_id, "status": s.status,
        "overall_score": perf.overall_score if perf else None,
        "performance": None if not perf else {"criterion_scores": perf.criterion_scores, "topic_performance": perf.topic_performance,
                                              "skill_performance": perf.skill_performance,
                                              "difficulty_progression": perf.difficulty_progression},
        "readiness": None if not ready else {"overall": ready.overall, "level": ready.level, "components": ready.components,
                                             "weights": ready.weights, "evidence": ready.evidence},
        "recommendations": [{"area": r.area, "area_type": r.area_type, "recommendation": r.recommendation,
                             "reason": r.reason, "priority": r.priority} for r in recs],
        "report_id": rep.id if rep else None,
    }


@router.get("/{session_id}/report", response_model=ReportOut)
def report(session_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> ReportOut:
    s = runtime.own_session(db, user, session_id)
    rep = _latest_report(db, s.id)
    if rep is None:
        raise NotFound("Report not available yet")
    out = ReportOut.model_validate(rep)
    if rep.file_id:
        out.download_url = presigned_url_for(db, rep.file_id, user, candidate_id=rep.candidate_id)
    return out


@router.get("/{session_id}/questions")
def questions(session_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    """Question/answer/evaluation detail with explanations (why scored, why next question)."""
    s = runtime.own_session(db, user, session_id)
    if user.is_student and s.status not in ("completed", "terminated"):
        return []  # evaluations are shown to candidates after the interview
    return session_questions(db, s.id)
