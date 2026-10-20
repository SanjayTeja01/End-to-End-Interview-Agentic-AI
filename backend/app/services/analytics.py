"""Dashboard read models — every number comes from stored evaluations/snapshots, scoped to the tenant."""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import lifecycle
from app.domain.performance import trend
from app.models import (
    Evaluation,
    Interview,
    InterviewCandidate,
    InterviewHistory,
    InterviewRecommendation,
    InterviewSession,
    Performance,
    Question,
    Readiness,
    User,
)
from app.models.enums import UserRole


def institution_overview(db: Session, institute_id: uuid.UUID) -> dict:
    today = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    students = db.execute(select(func.count()).select_from(User).where(
        User.institute_id == institute_id, User.role == UserRole.STUDENT)).scalar_one()
    interviews = list(db.execute(select(Interview).where(Interview.institute_id == institute_id)).scalars())
    eff = [lifecycle.effective_status(i.status, i.start_time, i.end_time) for i in interviews]
    sessions_today = db.execute(select(func.count()).select_from(InterviewSession).where(
        InterviewSession.institute_id == institute_id, InterviewSession.started_at >= today)).scalar_one()
    completed_sessions = db.execute(select(func.count()).select_from(InterviewSession).where(
        InterviewSession.institute_id == institute_id, InterviewSession.status == "completed")).scalar_one()
    live = db.execute(select(func.count()).select_from(InterviewSession).where(
        InterviewSession.institute_id == institute_id, InterviewSession.status.in_(["initializing", "in_progress"]))).scalar_one()
    avg = db.execute(select(func.avg(Performance.overall_score)).where(Performance.institute_id == institute_id)).scalar()

    # Overall performance over time (per day)
    day = func.date(Performance.created_at)
    by_day = db.execute(select(day, func.avg(Performance.overall_score), func.count()).where(
        Performance.institute_id == institute_id).group_by(day).order_by(day).limit(60)).all()
    by_role = db.execute(select(Performance.role_name, func.avg(Performance.overall_score), func.count()).where(
        Performance.institute_id == institute_id).group_by(Performance.role_name)).all()
    eligible = db.execute(select(func.count()).select_from(InterviewCandidate).where(
        InterviewCandidate.institute_id == institute_id,
        InterviewCandidate.eligibility_status.in_(["eligible", "assigned"]))).scalar_one()
    participated = db.execute(select(func.count()).select_from(InterviewSession).where(
        InterviewSession.institute_id == institute_id)).scalar_one()

    recent = db.execute(
        select(InterviewSession, User.full_name, Interview.name).join(User, User.id == InterviewSession.candidate_id)
        .join(Interview, Interview.id == InterviewSession.interview_id)
        .where(InterviewSession.institute_id == institute_id)
        .order_by(InterviewSession.updated_at.desc()).limit(10)).all()
    return {
        "total_students": students,
        "active_interviews": sum(1 for s in eff if s == lifecycle.ACTIVE),
        "completed_interviews": completed_sessions,
        "completed_campaigns": sum(1 for s in eff if s in (lifecycle.COMPLETED, lifecycle.CLOSED)),
        "live_sessions": live,
        "average_score": round(float(avg), 2) if avg is not None else None,
        "interviews_today": sessions_today,
        "performance_over_time": [{"date": str(d), "average": round(float(a), 2), "count": n} for d, a, n in by_day],
        "role_performance": [{"role": r, "average": round(float(a), 2), "count": n} for r, a, n in by_role],
        "participation": {"eligible": eligible, "participated": participated, "completed": completed_sessions,
                          "rate": round(participated / eligible, 3) if eligible else None},
        "recent_activity": [{"session_id": str(s.id), "candidate": name, "interview": iname, "status": s.status,
                             "updated_at": s.updated_at.isoformat()} for s, name, iname in recent],
    }


def candidate_overview(db: Session, institute_id: uuid.UUID, candidate_id: uuid.UUID) -> dict:
    perfs = list(db.execute(select(Performance, Interview.name).join(Interview, Interview.id == Performance.interview_id)
                            .where(Performance.candidate_id == candidate_id, Performance.institute_id == institute_id)
                            .order_by(Performance.created_at)).all())
    latest_ready = db.execute(select(Readiness).where(Readiness.candidate_id == candidate_id,
                                                      Readiness.institute_id == institute_id)
                              .order_by(Readiness.assessed_at.desc())).scalars().first()
    # skill / topic performance across all completed interviews, derived from evaluations
    skill_rows = db.execute(select(Evaluation.skill, func.avg(Evaluation.overall_score), func.count()).where(
        Evaluation.candidate_id == candidate_id, Evaluation.institute_id == institute_id, Evaluation.skill.is_not(None))
        .group_by(Evaluation.skill)).all()
    topic_rows = db.execute(select(Evaluation.topic, func.avg(Evaluation.overall_score), func.count()).where(
        Evaluation.candidate_id == candidate_id, Evaluation.institute_id == institute_id, Evaluation.topic.is_not(None))
        .group_by(Evaluation.topic)).all()
    role_rows: dict[str, list[float]] = {}
    for p, _ in perfs:
        role_rows.setdefault(p.role_name, []).append(p.overall_score)
    hist = list(db.execute(select(InterviewHistory).where(InterviewHistory.candidate_id == candidate_id,
                                                          InterviewHistory.institute_id == institute_id)
                           .order_by(InterviewHistory.completed_at.desc()).limit(5)).scalars())
    recs = list(db.execute(select(InterviewRecommendation).where(
        InterviewRecommendation.candidate_id == candidate_id, InterviewRecommendation.institute_id == institute_id,
        InterviewRecommendation.status == "open").order_by(InterviewRecommendation.created_at.desc(),
                                                           InterviewRecommendation.priority.desc()).limit(8)).scalars())
    scores = [p.overall_score for p, _ in perfs]
    strengths = sorted({t for h in hist for t in h.strong_topics})[:8]
    improvement = sorted({t for h in hist for t in h.weak_topics})[:8]
    return {
        "overall_score": round(sum(scores) / len(scores), 2) if scores else None,
        "latest_score": scores[-1] if scores else None,
        "completed_interviews": len(scores),
        "readiness": None if not latest_ready else {"overall": latest_ready.overall, "level": latest_ready.level,
                                                    "components": latest_ready.components, "role": latest_ready.role_name,
                                                    "assessed_at": latest_ready.assessed_at.isoformat()},
        "score_trend": trend([(name, p.overall_score) for p, name in perfs]),
        "score_over_time": [{"date": p.created_at.date().isoformat(), "interview": name, "score": p.overall_score}
                            for p, name in perfs],
        "skill_performance": [{"skill": s, "average": round(float(a), 2), "count": n} for s, a, n in skill_rows],
        "topic_performance": sorted([{"topic": t, "average": round(float(a), 2), "count": n} for t, a, n in topic_rows],
                                    key=lambda x: x["average"]),
        "role_performance": [{"role": r, "average": round(sum(v) / len(v), 2), "count": len(v)} for r, v in role_rows.items()],
        "strengths": strengths,
        "improvement_areas": improvement,
        "recommendations": [{"area": r.area, "recommendation": r.recommendation, "reason": r.reason,
                             "area_type": r.area_type} for r in recs],
    }


def candidate_history(db: Session, institute_id: uuid.UUID, candidate_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(InterviewSession, Interview, Performance, Readiness)
        .join(Interview, Interview.id == InterviewSession.interview_id)
        .outerjoin(Performance, Performance.session_id == InterviewSession.id)
        .outerjoin(Readiness, Readiness.session_id == InterviewSession.id)
        .where(InterviewSession.candidate_id == candidate_id, InterviewSession.institute_id == institute_id)
        .order_by(InterviewSession.created_at.desc())).all()
    return [{"session_id": str(s.id), "interview_id": str(i.id), "interview_name": i.name, "target_role": i.target_role,
             "status": s.status, "started_at": s.started_at.isoformat() if s.started_at else None,
             "ended_at": s.ended_at.isoformat() if s.ended_at else None,
             "overall_score": p.overall_score if p else None, "readiness": r.overall if r else None,
             "readiness_level": r.level if r else None, "questions": s.question_index} for s, i, p, r in rows]


def live_session_snapshot(db: Session, s: InterviewSession) -> dict:
    """Monitoring snapshot (transcript + current state + running performance)."""
    rows = db.execute(select(Question).where(Question.session_id == s.id).order_by(Question.sequence)).scalars().all()
    from app.models import Answer

    answers = {a.question_id: a for a in db.execute(select(Answer).where(Answer.session_id == s.id)).scalars()}
    evals = {e.question_id: e for e in db.execute(select(Evaluation).where(Evaluation.session_id == s.id)).scalars()}
    scores = [e.overall_score for e in evals.values()]
    return {
        "transcript": [{"sequence": q.sequence, "question": q.text, "topic": q.topic, "difficulty": q.difficulty,
                        "answer": answers[q.id].transcript if q.id in answers else None,
                        "answer_status": answers[q.id].status if q.id in answers else None,
                        "score": evals[q.id].overall_score if q.id in evals else None,
                        "next_question_reason": evals[q.id].next_question_reason if q.id in evals else None}
                       for q in rows],
        "running_score": round(sum(scores) / len(scores), 2) if scores else None,
        "connection": s.connection or {},
    }
