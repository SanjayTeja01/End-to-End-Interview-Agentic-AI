"""Candidate skill estimation and gap computation (persisted with evidence)."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.skills import SkillEvidence, compute_gaps
from app.models import CandidateSkill, Interview, RoleSkill, SkillGap


def approved_requirements(db: Session, interview: Interview) -> list[RoleSkill]:
    return list(db.execute(select(RoleSkill).where(
        RoleSkill.interview_id == interview.id, RoleSkill.institute_id == interview.institute_id,
        RoleSkill.approval_status == "approved")).scalars())


def evidence_by_skill(db: Session, candidate_id: uuid.UUID, institute_id: uuid.UUID) -> dict[str, list[SkillEvidence]]:
    out: dict[str, list[SkillEvidence]] = {}
    for cs in db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id,
                                                      CandidateSkill.institute_id == institute_id)).scalars():
        note = "; ".join(str(e.get("note") or e.get("quote") or "") for e in (cs.evidence or [])[:2])
        out.setdefault(cs.skill_key, []).append(SkillEvidence(cs.source, cs.proficiency, cs.confidence, note))
    return out


def compute_and_store(db: Session, *, candidate_id: uuid.UUID, interview: Interview) -> list[dict]:
    reqs = approved_requirements(db, interview)
    gaps = compute_gaps(
        [{"skill": r.skill, "skill_key": r.skill_key, "required_level": r.required_level,
          "importance_weight": r.importance_weight} for r in reqs],
        evidence_by_skill(db, candidate_id, interview.institute_id),
    )
    db.execute(delete(SkillGap).where(SkillGap.candidate_id == candidate_id, SkillGap.interview_id == interview.id))
    key_by_skill = {r.skill: r.skill_key for r in reqs}
    rows = []
    for g in gaps:
        db.add(SkillGap(candidate_id=candidate_id, role_id=interview.role_id, interview_id=interview.id,
                        institute_id=interview.institute_id, skill=g.skill, skill_key=key_by_skill[g.skill],
                        required_level=g.required_level, candidate_level=g.candidate_level, gap=g.gap,
                        priority=g.priority, evidence=g.evidence))
        rows.append({"skill": g.skill, "skill_key": key_by_skill[g.skill], "required_level": g.required_level,
                     "candidate_level": g.candidate_level, "gap": g.gap, "priority": g.priority})
    db.flush()
    return rows
