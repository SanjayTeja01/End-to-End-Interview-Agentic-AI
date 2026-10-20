from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_student
from app.core.database import get_db
from app.models import CandidateProfile, CandidateSkill, SkillGap, User
from app.schemas.profile import CandidateSkillOut, ProfileIn, ProfileOut, SkillGapOut
from app.services.interviews import refresh_for_candidate

router = APIRouter(tags=["profile"])


def _profile(db: Session, user: CurrentUser) -> CandidateProfile:
    return db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id,
                                                     CandidateProfile.institute_id == user.institute_id)).scalar_one()


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> CandidateProfile:
    return _profile(db, user)


@router.put("/profile", response_model=ProfileOut)
def update_profile(data: ProfileIn, user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> CandidateProfile:
    p = _profile(db, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(p, k, v)
    if data.target_roles is not None:
        p.target_roles = list(dict.fromkeys(r.strip() for r in data.target_roles if r.strip()))
    db.flush()
    if data.target_roles is not None:
        refresh_for_candidate(db, db.get(User, user.id))
    db.commit()
    return p


@router.get("/skills", response_model=list[CandidateSkillOut])
def my_skills(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> list[CandidateSkill]:
    return list(db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == user.id)
                           .order_by(CandidateSkill.proficiency.desc())).scalars())


@router.get("/skills/gaps", response_model=list[SkillGapOut])
def my_gaps(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> list[SkillGap]:
    return list(db.execute(select(SkillGap).where(SkillGap.candidate_id == user.id)
                           .order_by(SkillGap.priority.desc())).scalars())
