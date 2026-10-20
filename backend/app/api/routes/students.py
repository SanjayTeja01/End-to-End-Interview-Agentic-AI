from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_institution, require_institution_admin
from app.core.database import get_db
from app.core.errors import Conflict, NotFound
from app.models import (Answer, CandidateProfile, CandidateSkill, FileObject, InterviewSession, Performance, Question,
                        Resume, SkillGap, User)
from app.models.enums import UserRole
from app.services import analytics
from storage.minio.client import get_storage

router = APIRouter(prefix="/students", tags=["students"])


def _student(db: Session, user: CurrentUser, student_id: uuid.UUID) -> User:
    s = db.execute(select(User).where(User.id == student_id, User.institute_id == user.institute_id,
                                      User.role == UserRole.STUDENT)).scalar_one_or_none()
    if s is None:
        raise NotFound("Student not found")
    return s


@router.get("")
def list_students(user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db),
                  q: str | None = Query(default=None, max_length=100), limit: int = Query(default=100, le=500),
                  offset: int = Query(default=0, ge=0)) -> dict:
    base = select(User).where(User.institute_id == user.institute_id, User.role == UserRole.STUDENT)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    users = list(db.execute(base.order_by(User.full_name).limit(limit).offset(offset)).scalars())
    ids = [u.id for u in users]
    profiles = {p.user_id: p for p in db.execute(select(CandidateProfile).where(CandidateProfile.user_id.in_(ids))).scalars()}
    scores = dict(db.execute(select(Performance.candidate_id, func.avg(Performance.overall_score)).where(
        Performance.candidate_id.in_(ids)).group_by(Performance.candidate_id)).all())
    counts = dict(db.execute(select(InterviewSession.candidate_id, func.count()).where(
        InterviewSession.candidate_id.in_(ids), InterviewSession.status == "completed").group_by(InterviewSession.candidate_id)).all())
    return {"total": total, "items": [{
        "id": str(u.id), "full_name": u.full_name, "email": u.email,
        "target_roles": profiles[u.id].target_roles if u.id in profiles else [],
        "average_score": round(float(scores[u.id]), 2) if u.id in scores else None,
        "completed_interviews": counts.get(u.id, 0), "created_at": u.created_at.isoformat()} for u in users]}


@router.get("/{student_id}")
def get_student(student_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    s = _student(db, user, student_id)
    p = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == s.id)).scalar_one_or_none()
    resume = db.execute(select(Resume).where(Resume.candidate_id == s.id, Resume.is_current.is_(True))).scalar_one_or_none()
    skills = db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == s.id)).scalars().all()
    gaps = db.execute(select(SkillGap).where(SkillGap.candidate_id == s.id).order_by(SkillGap.priority.desc()).limit(30)).scalars().all()
    active = db.execute(select(InterviewSession).where(InterviewSession.candidate_id == s.id,
                                                       InterviewSession.status.in_(["initializing", "in_progress"]))).scalars().first()
    return {
        "student": {"id": str(s.id), "full_name": s.full_name, "email": s.email},
        "profile": None if not p else {k: getattr(p, k) for k in (
            "headline", "summary", "education", "experience", "projects", "technical_skills", "non_technical_skills",
            "technologies", "certifications", "achievements", "target_roles")},
        "resume": None if not resume else {"id": str(resume.id), "version": resume.version,
                                           "processing_status": resume.processing_status, "analysis": resume.analysis},
        "skills": [{"skill": k.skill, "proficiency": k.proficiency, "source": k.source, "confidence": k.confidence,
                    "evidence": k.evidence} for k in skills],
        "skill_gaps": [{"skill": g.skill, "required_level": g.required_level, "candidate_level": g.candidate_level,
                        "gap": g.gap, "priority": g.priority, "interview_id": str(g.interview_id) if g.interview_id else None}
                       for g in gaps],
        "performance": analytics.candidate_overview(db, user.institute_id, s.id),
        "history": analytics.candidate_history(db, user.institute_id, s.id),
        "active_session_id": str(active.id) if active else None,
    }


@router.delete("/{student_id}", status_code=204)
def delete_student(student_id: uuid.UUID, user: CurrentUser = Depends(require_institution_admin),
                   db: Session = Depends(get_db)) -> None:
    """Permanently delete a student's account and everything recorded about them (profile, resume, sessions,
    answers, evaluations, reports, and their uploaded/recorded files in object storage)."""
    s = _student(db, user, student_id)
    if db.execute(select(InterviewSession.id).where(InterviewSession.candidate_id == s.id,
                                                   InterviewSession.status.in_(["initializing", "in_progress"]))).first():
        raise Conflict("Student has an interview in progress; end it before removing the student")
    sessions = select(InterviewSession.id).where(InterviewSession.candidate_id == s.id)
    file_ids = {*db.execute(select(FileObject.id).where(FileObject.owner_id == s.id)).scalars(),
                *db.execute(select(Question.tts_file_id).where(Question.session_id.in_(sessions))).scalars(),
                *db.execute(select(Answer.audio_file_id).where(Answer.candidate_id == s.id)).scalars(),
                *db.execute(select(Answer.video_file_id).where(Answer.candidate_id == s.id)).scalars()} - {None}
    keys = list(db.execute(select(FileObject.object_key).where(FileObject.id.in_(file_ids))).scalars()) if file_ids else []
    # Sessions, answers, evaluations, reports, profile, resumes and skills go with the user via ON DELETE CASCADE.
    db.execute(delete(User).where(User.id == s.id))
    if file_ids:
        db.execute(delete(FileObject).where(FileObject.id.in_(file_ids)))
    db.commit()
    storage = get_storage()
    for k in keys:  # objects go after the commit so a failed delete never leaves rows pointing at nothing
        try:
            storage.delete(k)
        except Exception:  # noqa: BLE001  an orphaned object is harmless; the account is already gone
            pass
