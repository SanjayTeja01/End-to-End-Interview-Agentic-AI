from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_institution, require_student
from app.core.database import get_db
from app.models import InterviewRecommendation, Readiness
from app.schemas.results import RecommendationOut
from app.services import analytics

router = APIRouter(tags=["performance"])


@router.get("/overview/student")
def student_overview(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    return analytics.candidate_overview(db, user.institute_id, user.id)


@router.get("/overview/institution")
def institution_overview(user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    return analytics.institution_overview(db, user.institute_id)


@router.get("/performance")
def performance(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    o = analytics.candidate_overview(db, user.institute_id, user.id)
    return {k: o[k] for k in ("overall_score", "latest_score", "score_trend", "score_over_time", "skill_performance",
                              "topic_performance", "role_performance")}


@router.get("/performance/history")
def history(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    return analytics.candidate_history(db, user.institute_id, user.id)


@router.get("/readiness")
def readiness(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Readiness).where(Readiness.candidate_id == user.id).order_by(Readiness.assessed_at.desc())).scalars()
    return [{"session_id": str(r.session_id) if r.session_id else None, "role": r.role_name, "overall": r.overall,
             "level": r.level, "components": r.components, "evidence": r.evidence, "weights": r.weights,
             "assessed_at": r.assessed_at.isoformat()} for r in rows]


@router.get("/recommendations", response_model=list[RecommendationOut])
def recommendations(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> list:
    return list(db.execute(select(InterviewRecommendation).where(InterviewRecommendation.candidate_id == user.id)
                           .order_by(InterviewRecommendation.created_at.desc(), InterviewRecommendation.priority.desc())
                           .limit(50)).scalars())
