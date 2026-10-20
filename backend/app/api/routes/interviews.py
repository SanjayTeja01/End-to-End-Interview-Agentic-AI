from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_institution, require_student
from app.core.database import get_db
from app.core.errors import NotFound
from app.domain import lifecycle
from app.models import Interview, InterviewCandidate, InterviewSession, Performance, RoleSkill, User
from app.schemas.common import JobOut
from app.schemas.interview import (
    AssignCandidatesIn,
    CandidateInterviewOut,
    InterviewCandidateRow,
    InterviewCreate,
    InterviewDetailOut,
    InterviewOut,
    InterviewStats,
    InterviewUpdate,
    RoleSkillOut,
    SkillsReplaceIn,
)
from app.services import interviews as svc
from app.services import jobs, runtime
from app.services.tenancy import get_scoped

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _out(db: Session, iv: Interview, stats: dict | None = None, detail: bool = False) -> dict:
    model = InterviewDetailOut if detail else InterviewOut
    o = model.model_validate(iv)
    o.effective_status = lifecycle.effective_status(iv.status, iv.start_time, iv.end_time)
    if stats is not None:
        o.stats = InterviewStats(**stats)
    if detail:
        o.skills = [RoleSkillOut.model_validate(r) for r in db.execute(
            select(RoleSkill).where(RoleSkill.interview_id == iv.id).order_by(RoleSkill.importance_weight.desc())).scalars()]
    return o.model_dump(mode="json")


def _candidate_view(db: Session, user: CurrentUser, iv: Interview) -> CandidateInterviewOut | None:
    candidate = db.get(User, user.id)
    res = svc.evaluate_candidate(db, iv, candidate, use_semantic=True)
    if not res.visible:
        return None
    s = db.execute(select(InterviewSession).where(InterviewSession.interview_id == iv.id,
                                                  InterviewSession.candidate_id == user.id)).scalar_one_or_none()
    return CandidateInterviewOut(
        id=iv.id, name=iv.name, target_role=iv.target_role, interview_type=iv.interview_type,
        duration_minutes=iv.duration_minutes, question_count=iv.question_count, start_time=iv.start_time,
        end_time=iv.end_time, status=lifecycle.effective_status(iv.status, iv.start_time, iv.end_time),
        joinable=res.joinable and (s is None or s.status in runtime.ACTIVE_STATES), eligibility_reason=res.reason,
        participation_status=(s.status if s else "not_started"), session_id=s.id if s else None)


@router.get("")
def list_interviews(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db),
                    status: str | None = Query(default=None)) -> list[dict]:
    """Institution: all campaigns with stats. Student: only interviews they are eligible for (server-side)."""
    q = select(Interview).where(Interview.institute_id == user.institute_id).order_by(Interview.created_at.desc())
    if user.is_student:
        q = q.where(Interview.status.in_([lifecycle.ACTIVE, lifecycle.SCHEDULED]))
        out = [_candidate_view(db, user, iv) for iv in db.execute(q).scalars()]
        return [o.model_dump(mode="json") for o in out if o]
    rows = list(db.execute(q).scalars())
    if status:
        rows = [r for r in rows if lifecycle.effective_status(r.status, r.start_time, r.end_time) == status]
    stats = svc.stats_for(db, [r.id for r in rows])
    return [_out(db, r, stats[r.id]) for r in rows]


@router.post("", status_code=201)
def create(data: InterviewCreate, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    from app.workers.interview_tasks import infer_requirements

    iv, needs = svc.create_interview(db, user, data)
    job = None
    if needs:
        job = jobs.create_job(db, institute_id=user.institute_id, owner_id=user.id, job_type="skill_inference",
                              entity_type="interview", entity_id=iv.id)
    db.commit()
    if job:
        jobs.dispatch(infer_requirements, str(iv.id), str(job.id), job=job, db=db)
    return {"interview": _out(db, iv, detail=True), "job": JobOut.model_validate(job).model_dump(mode="json") if job else None}


@router.get("/{interview_id}")
def get(interview_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    if user.is_student:
        view = _candidate_view(db, user, iv)
        if view is None:
            raise NotFound("Interview not found")  # no existence leak for ineligible candidates
        return view.model_dump(mode="json")
    return _out(db, iv, svc.stats_for(db, [iv.id])[iv.id], detail=True)


@router.put("/{interview_id}")
def update(interview_id: uuid.UUID, data: InterviewUpdate, user: CurrentUser = Depends(require_institution),
           db: Session = Depends(get_db)) -> dict:
    iv = svc.update_interview(db, user, interview_id, data)
    db.commit()
    return _out(db, iv, detail=True)


@router.delete("/{interview_id}", status_code=204)
def delete(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> None:
    svc.delete_interview(db, user, interview_id)
    db.commit()


@router.put("/{interview_id}/skills")
def replace_skills(interview_id: uuid.UUID, data: SkillsReplaceIn, user: CurrentUser = Depends(require_institution),
                   db: Session = Depends(get_db)) -> dict:
    iv = svc.replace_skills(db, user, interview_id, data.skills)
    db.commit()
    return _out(db, iv, detail=True)


@router.post("/{interview_id}/infer-skills", status_code=202)
def reinfer(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    from app.workers.interview_tasks import infer_requirements

    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    if iv.status not in lifecycle.EDITABLE:
        from app.core.errors import InvalidTransition

        raise InvalidTransition("Requirements are locked")
    iv.skill_approval_state = "generating"
    job = jobs.create_job(db, institute_id=user.institute_id, owner_id=user.id, job_type="skill_inference",
                          entity_type="interview", entity_id=iv.id)
    jobs.dispatch(infer_requirements, str(iv.id), str(job.id), job=job, db=db)
    return JobOut.model_validate(job).model_dump(mode="json")


@router.post("/{interview_id}/approve")
def approve(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    iv = svc.approve(db, user, interview_id)
    db.commit()
    return _out(db, iv, detail=True)


@router.post("/{interview_id}/activate")
def activate(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    iv = svc.activate(db, user, interview_id)
    db.commit()
    return _out(db, iv, detail=True)


@router.post("/{interview_id}/close")
def close(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    target = lifecycle.CLOSED if lifecycle.effective_status(iv.status, iv.start_time, iv.end_time) in (
        lifecycle.ACTIVE, lifecycle.COMPLETED) else lifecycle.CANCELLED
    iv = svc.change_status(db, user, interview_id, target)
    db.commit()
    return _out(db, iv, detail=True)


@router.post("/{interview_id}/cancel")
def cancel(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> dict:
    iv = svc.change_status(db, user, interview_id, lifecycle.CANCELLED)
    db.commit()
    return _out(db, iv, detail=True)


@router.post("/{interview_id}/candidates")
def assign(interview_id: uuid.UUID, data: AssignCandidatesIn, user: CurrentUser = Depends(require_institution),
           db: Session = Depends(get_db)) -> dict:
    n = svc.assign(db, user, interview_id, data.candidate_ids, data.action)
    db.commit()
    return {"updated": n}


@router.get("/{interview_id}/candidates", response_model=list[InterviewCandidateRow])
def candidates(interview_id: uuid.UUID, user: CurrentUser = Depends(require_institution), db: Session = Depends(get_db)) -> list[dict]:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    rows = db.execute(
        select(InterviewCandidate, User, InterviewSession, Performance)
        .join(User, User.id == InterviewCandidate.candidate_id)
        .outerjoin(InterviewSession, (InterviewSession.interview_id == iv.id) & (InterviewSession.candidate_id == User.id))
        .outerjoin(Performance, Performance.session_id == InterviewSession.id)
        .where(InterviewCandidate.interview_id == iv.id, InterviewCandidate.institute_id == user.institute_id)
        .order_by(User.full_name)).all()
    return [{"candidate_id": u.id, "full_name": u.full_name, "email": u.email, "eligibility_status": ic.eligibility_status,
             "participation_status": ic.participation_status, "match_score": ic.match_score,
             "session_id": s.id if s else None, "session_status": s.status if s else None,
             "score": p.overall_score if p else None, "progress": s.progress if s else None} for ic, u, s, p in rows]


@router.post("/{interview_id}/start")
def start(interview_id: uuid.UUID, user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    s = runtime.start_or_resume(db, user, interview_id)
    return {"session_id": str(s.id), "status": s.status}
