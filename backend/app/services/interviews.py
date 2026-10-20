"""Interview campaign management: creation, requirements, approval, lifecycle, eligibility, statistics."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import Conflict, InvalidTransition, NotFound, ValidationFailed
from app.core.logging import log_event
from app.domain import eligibility as elig
from app.domain import lifecycle
from app.domain.text import normalize_key
from app.models import (
    CandidateProfile,
    Interview,
    InterviewCandidate,
    InterviewSession,
    KnowledgeDocument,
    Performance,
    Role,
    RoleSkill,
    User,
)
from app.models.enums import UserRole
from app.schemas.interview import InterviewCreate, InterviewUpdate, RequiredSkillIn
from app.services.tenancy import get_scoped

log = logging.getLogger(__name__)


def get_or_create_role(db: Session, institute_id: uuid.UUID, name: str, description: str | None = None) -> Role:
    key = normalize_key(name)
    role = db.execute(select(Role).where(Role.institute_id == institute_id, Role.normalized_name == key)).scalar_one_or_none()
    if role is None:
        role = Role(institute_id=institute_id, name=name.strip(), normalized_name=key, description=description)
        db.add(role)
        db.flush()
    return role


def _validate_knowledge_ids(db: Session, user: CurrentUser, ids: list[uuid.UUID]) -> list[str]:
    if not ids:
        return []
    found = {r for (r,) in db.execute(select(KnowledgeDocument.id).where(
        KnowledgeDocument.institute_id == user.institute_id, KnowledgeDocument.id.in_(ids)))}
    missing = set(ids) - found
    if missing:
        raise ValidationFailed("Unknown knowledge documents", details={"ids": [str(m) for m in missing]})
    return [str(i) for i in ids]


def _write_skills(db: Session, interview: Interview, skills: list[RequiredSkillIn], *, source: str, approval: str,
                  rationale: dict[str, str] | None = None) -> None:
    db.execute(delete(RoleSkill).where(RoleSkill.interview_id == interview.id))
    seen = set()
    for s in skills:
        key = normalize_key(s.skill)
        if key in seen:
            continue
        seen.add(key)
        db.add(RoleSkill(role_id=interview.role_id, interview_id=interview.id, institute_id=interview.institute_id,
                         skill=s.skill.strip(), skill_key=key, required_level=s.required_level,
                         importance_weight=s.importance_weight, topics=s.topics or [s.skill.strip()],
                         question_categories=s.question_categories, source=source, approval_status=approval,
                         rationale=(rationale or {}).get(key)))
    db.flush()


def create_interview(db: Session, user: CurrentUser, data: InterviewCreate) -> tuple[Interview, bool]:
    """Returns (interview, needs_inference)."""
    if not data.required_skills and not data.infer_skills:
        raise ValidationFailed("Provide required skills or enable AI skill inference")
    role = get_or_create_role(db, user.institute_id, data.target_role)
    iv = Interview(
        institute_id=user.institute_id, role_id=role.id, name=data.name, target_role=role.name,
        job_description=data.job_description, duration_minutes=data.duration_minutes, start_time=data.start_time,
        end_time=data.end_time, interview_type=data.interview_type, question_count=data.question_count,
        initial_difficulty=data.initial_difficulty, adaptive_mode=data.adaptive_mode,
        evaluation_config=data.evaluation_config.model_dump(exclude_none=True),
        readiness_config=data.readiness_config.model_dump(exclude_none=True),
        eligibility_config=data.eligibility_config.model_dump(),
        knowledge_document_ids=_validate_knowledge_ids(db, user, data.knowledge_document_ids),
        record_media=data.record_media, created_by=user.id, status=lifecycle.DRAFT,
    )
    db.add(iv)
    db.flush()
    if data.required_skills:
        # Institution-provided skills are validated by the schema and become the approved requirements.
        _write_skills(db, iv, data.required_skills, source="institution", approval="approved")
        iv.skill_approval_state = "not_required"
        iv.status = lifecycle.APPROVED
        needs = False
    else:
        iv.skill_approval_state = "generating"
        needs = True
    log_event(log, "interview_created", interview_id=str(iv.id), institute_id=str(user.institute_id),
              infer=needs)
    return iv, needs


def apply_inferred_skills(db: Session, interview: Interview, proposals) -> None:  # noqa: ANN001
    skills = [RequiredSkillIn(skill=p.skill, required_level=p.required_level, importance_weight=round(p.importance / 5, 2),
                              topics=p.topics, question_categories=p.question_categories) for p in proposals.skills]
    _write_skills(db, interview, skills, source="ai_inferred", approval="pending",
                  rationale={normalize_key(p.skill): p.rationale for p in proposals.skills})
    interview.skill_approval_state = "pending"
    if interview.status != lifecycle.PENDING:
        lifecycle.assert_transition(interview.status, lifecycle.PENDING)
        interview.status = lifecycle.PENDING


def update_interview(db: Session, user: CurrentUser, interview_id: uuid.UUID, data: InterviewUpdate) -> Interview:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    if iv.status not in lifecycle.EDITABLE:
        raise InvalidTransition(f"Interview cannot be edited in status '{iv.status}'")
    payload = data.model_dump(exclude_unset=True)
    if "knowledge_document_ids" in payload:
        payload["knowledge_document_ids"] = _validate_knowledge_ids(db, user, data.knowledge_document_ids or [])
    for k in ("evaluation_config", "readiness_config", "eligibility_config"):
        if k in payload and payload[k] is not None:
            payload[k] = getattr(data, k).model_dump(exclude_none=True)
    for k, v in payload.items():
        setattr(iv, k, v)
    if iv.start_time and iv.end_time and iv.end_time <= iv.start_time:
        raise ValidationFailed("end_time must be after start_time")
    db.flush()
    return iv


def replace_skills(db: Session, user: CurrentUser, interview_id: uuid.UUID, skills: list[RequiredSkillIn]) -> Interview:
    """Institution review/edit. AI-inferred requirements (edited or not) remain pending until explicitly approved."""
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    if iv.status not in lifecycle.EDITABLE:
        raise InvalidTransition("Requirements are locked once the interview is scheduled or active")
    ai_flow = iv.skill_approval_state in ("pending", "approved", "generating")
    if iv.skill_approval_state == "generating":
        raise Conflict("Requirements are still being generated")
    if ai_flow:
        _write_skills(db, iv, skills, source="ai_inferred", approval="pending")
        iv.skill_approval_state = "pending"
        if iv.status != lifecycle.PENDING:
            lifecycle.assert_transition(iv.status, lifecycle.PENDING)
            iv.status = lifecycle.PENDING
    else:
        _write_skills(db, iv, skills, source="institution", approval="approved")
    db.flush()
    return iv


def approve(db: Session, user: CurrentUser, interview_id: uuid.UUID) -> Interview:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    rows = list(db.execute(select(RoleSkill).where(RoleSkill.interview_id == iv.id)).scalars())
    if not rows:
        raise ValidationFailed("No requirements to approve")
    if iv.skill_approval_state == "generating":
        raise Conflict("Requirements are still being generated")
    try:
        lifecycle.assert_transition(iv.status, lifecycle.APPROVED)
    except lifecycle.TransitionError as exc:
        raise InvalidTransition(str(exc)) from exc
    for r in rows:
        r.approval_status = "approved"
    iv.skill_approval_state = "approved" if any(r.source == "ai_inferred" for r in rows) else "not_required"
    iv.status = lifecycle.APPROVED
    db.flush()
    log_event(log, "interview_requirements_approved", interview_id=str(iv.id), by=str(user.id))
    return iv


def activate(db: Session, user: CurrentUser, interview_id: uuid.UUID) -> Interview:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    approved = db.execute(select(func.count()).select_from(RoleSkill).where(
        RoleSkill.interview_id == iv.id, RoleSkill.approval_status == "approved")).scalar_one()
    ok, msg = lifecycle.can_activate(status=iv.status, skill_approval_state=iv.skill_approval_state,
                                     has_approved_skills=approved > 0)
    if not ok:
        raise InvalidTransition(msg)
    if iv.end_time and iv.end_time <= datetime.now(timezone.utc):
        raise ValidationFailed("End time is in the past")
    target = lifecycle.activation_target(iv.start_time)
    lifecycle.assert_transition(iv.status, target)
    iv.status = target
    db.flush()
    refresh_eligibility(db, iv)
    log_event(log, "interview_activated", interview_id=str(iv.id), status=target)
    return iv


def change_status(db: Session, user: CurrentUser, interview_id: uuid.UUID, target: str) -> Interview:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    try:
        lifecycle.assert_transition(lifecycle.effective_status(iv.status, iv.start_time, iv.end_time), target)
    except lifecycle.TransitionError as exc:
        raise InvalidTransition(str(exc)) from exc
    iv.status = target
    db.flush()
    return iv


def delete_interview(db: Session, user: CurrentUser, interview_id: uuid.UUID) -> None:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    has_sessions = db.execute(select(func.count()).select_from(InterviewSession).where(
        InterviewSession.interview_id == iv.id)).scalar_one()
    if has_sessions:
        # Keep history: interviews with sessions are cancelled/closed, never deleted.
        raise Conflict("Interview has candidate sessions; close or cancel it instead")
    db.delete(iv)
    db.flush()


# ------------------------------------------------------------------ eligibility
_SEMANTIC_CACHE: dict[tuple[str, str], float] = {}


def _semantic_scores(interview_role: str, roles: list[str]) -> dict[str, float]:
    """Optional embedding similarity between role names (adds a match signal; never grants access alone).
    Cached per (role, role) pair so eligibility refreshes don't repeat embedding calls."""
    if not roles:
        return {}
    a = normalize_key(interview_role)
    missing = [r for r in roles if (a, normalize_key(r)) not in _SEMANTIC_CACHE]
    if missing:
        try:
            from rag.embeddings.providers import get_embeddings

            vecs = get_embeddings().embed_documents([interview_role, *missing])
            for r, v in zip(missing, vecs[1:]):
                _SEMANTIC_CACHE[(a, normalize_key(r))] = round(sum(x * y for x, y in zip(vecs[0], v)), 3)
        except Exception:  # noqa: BLE001
            return {r: _SEMANTIC_CACHE[(a, normalize_key(r))] for r in roles if (a, normalize_key(r)) in _SEMANTIC_CACHE}
    return {r: _SEMANTIC_CACHE[(a, normalize_key(r))] for r in roles}


def evaluate_candidate(db: Session, interview: Interview, candidate: User, *, use_semantic: bool = False,
                       now: datetime | None = None) -> elig.EligibilityResult:
    profile = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == candidate.id)).scalar_one_or_none()
    roles = list(profile.target_roles) if profile else []
    ic = db.execute(select(InterviewCandidate).where(InterviewCandidate.interview_id == interview.id,
                                                     InterviewCandidate.candidate_id == candidate.id)).scalar_one_or_none()
    assignment = ic.eligibility_status if ic and ic.eligibility_status in ("assigned", "revoked") else None
    semantic = None
    if use_semantic and roles and elig.role_match_score(interview.target_role, roles) < \
            float((interview.eligibility_config or {}).get("min_similarity", elig.DEFAULT_MIN_SIMILARITY)):  # noqa: E501
        semantic = _semantic_scores(interview.target_role, roles)
    return elig.evaluate(
        candidate_institute_id=candidate.institute_id, interview_institute_id=interview.institute_id,
        candidate_active=candidate.status == "active" and candidate.role == UserRole.STUDENT,
        interview_status=interview.status, start=interview.start_time, end=interview.end_time,
        interview_role=interview.target_role, candidate_roles=roles,
        eligibility_config=interview.eligibility_config or {}, assignment_status=assignment,
        semantic_scores=semantic, now=now)


def refresh_eligibility(db: Session, interview: Interview, candidates: list[User] | None = None) -> None:
    """Materialise eligibility rows for listing and statistics. Join-time checks re-evaluate authoritatively."""
    if candidates is None:
        candidates = list(db.execute(select(User).where(User.institute_id == interview.institute_id,
                                                        User.role == UserRole.STUDENT)).scalars())
    for c in candidates:
        res = evaluate_candidate(db, interview, c, use_semantic=True)
        ic = db.execute(select(InterviewCandidate).where(InterviewCandidate.interview_id == interview.id,
                                                         InterviewCandidate.candidate_id == c.id)).scalar_one_or_none()
        if ic is None:
            if not res.eligible:
                continue
            ic = InterviewCandidate(interview_id=interview.id, candidate_id=c.id, institute_id=interview.institute_id)
            db.add(ic)
        if ic.eligibility_status not in ("assigned", "revoked"):
            ic.eligibility_status = "eligible" if res.eligible else "ineligible"
        ic.eligibility_reason = res.reason
        ic.match_score = res.match_score
    db.flush()


def refresh_for_candidate(db: Session, candidate: User) -> None:
    for iv in db.execute(select(Interview).where(Interview.institute_id == candidate.institute_id,
                                                 Interview.status.in_([lifecycle.ACTIVE, lifecycle.SCHEDULED]))).scalars():
        refresh_eligibility(db, iv, [candidate])


def assign(db: Session, user: CurrentUser, interview_id: uuid.UUID, candidate_ids: list[uuid.UUID], action: str) -> int:
    iv = get_scoped(db, Interview, interview_id, user, label="Interview")
    students = list(db.execute(select(User).where(User.id.in_(candidate_ids), User.institute_id == user.institute_id,
                                                  User.role == UserRole.STUDENT)).scalars())
    if len(students) != len(set(candidate_ids)):
        raise NotFound("One or more students not found")
    for s in students:
        ic = db.execute(select(InterviewCandidate).where(InterviewCandidate.interview_id == iv.id,
                                                         InterviewCandidate.candidate_id == s.id)).scalar_one_or_none()
        if ic is None:
            ic = InterviewCandidate(interview_id=iv.id, candidate_id=s.id, institute_id=iv.institute_id)
            db.add(ic)
        ic.eligibility_status = "assigned" if action == "assign" else "revoked"
        ic.invited_by = user.id
        ic.eligibility_reason = "Assigned by institution" if action == "assign" else "Access revoked by institution"
    db.flush()
    return len(students)


def stats_for(db: Session, interview_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    out = {i: {"candidate_count": 0, "participated": 0, "in_progress": 0, "completed": 0, "average_score": None}
           for i in interview_ids}
    if not interview_ids:
        return out
    for iid, n in db.execute(select(InterviewCandidate.interview_id, func.count()).where(
            InterviewCandidate.interview_id.in_(interview_ids),
            InterviewCandidate.eligibility_status.in_(["eligible", "assigned"])).group_by(InterviewCandidate.interview_id)):
        out[iid]["candidate_count"] = n
    for iid, status, n in db.execute(select(InterviewSession.interview_id, InterviewSession.status, func.count()).where(
            InterviewSession.interview_id.in_(interview_ids)).group_by(InterviewSession.interview_id, InterviewSession.status)):
        out[iid]["participated"] += n
        if status in ("initializing", "in_progress", "finalizing"):
            out[iid]["in_progress"] += n
        elif status == "completed":
            out[iid]["completed"] += n
    for iid, avg in db.execute(select(Performance.interview_id, func.avg(Performance.overall_score)).where(
            Performance.interview_id.in_(interview_ids)).group_by(Performance.interview_id)):
        out[iid]["average_score"] = round(float(avg), 2) if avg is not None else None
    return out
