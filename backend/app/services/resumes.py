"""Resume intelligence pipeline: validate → store → extract → clean → sections → analyse → persist."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agents.resume_analyzer import ResumeAnalyzerAgent, detect_sections
from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.logging import log_event
from app.domain.text import normalize_key
from app.models import CandidateProfile, CandidateSkill, FileObject, Resume, User
from app.services.files import DOC_MIME, store_file, validate_upload
from rag.cleaning.cleaner import clean_text
from rag.extraction.extractors import extract
from storage.minio.client import get_storage
from storage.minio.keys import resume_key

log = logging.getLogger(__name__)
RESUME_TYPES = {k: DOC_MIME[k] for k in ("pdf", "docx")}


def upload(db: Session, user: CurrentUser, data: bytes, filename: str | None) -> Resume:
    vf = validate_upload(data, filename, allowed=RESUME_TYPES, max_mb=get_settings().max_upload_mb)
    f = store_file(db, vf, key=resume_key(user.institute_id, user.id, vf.ext), owner_id=user.id,
                   institute_id=user.institute_id, file_type="resume")
    version = (db.execute(select(func.max(Resume.version)).where(Resume.candidate_id == user.id)).scalar() or 0) + 1
    db.execute(update(Resume).where(Resume.candidate_id == user.id).values(is_current=False))
    r = Resume(candidate_id=user.id, institute_id=user.institute_id, file_id=f.id, version=version, is_current=True,
               processing_status="pending")
    db.add(r)
    db.flush()
    return r


def process(db: Session, resume_id: uuid.UUID) -> None:
    r = db.get(Resume, resume_id)
    f = db.get(FileObject, r.file_id)
    r.processing_status = "processing"
    db.commit()
    try:
        raw = get_storage().get_bytes(f.object_key)
        extracted = extract(raw, f.object_key.rsplit(".", 1)[-1])
        text = clean_text(extracted.text)
        sections = detect_sections(text)
        analysis = ResumeAnalyzerAgent().analyze(text, sections)
        r.extraction_meta = {"chars": len(text), **extracted.meta, "sections_detected": sorted(sections)}
        r.sections = {k: v[:4000] for k, v in sections.items()}
        r.analysis = analysis.model_dump()
        _apply_to_profile(db, r, analysis)
        r.processing_status = "completed"
        r.error = None
        db.commit()
        log_event(log, "resume_processed", resume_id=str(r.id), skills=len(analysis.technical_skills))
        from app.services.interviews import refresh_for_candidate

        refresh_for_candidate(db, db.get(User, r.candidate_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        r = db.get(Resume, resume_id)
        r.processing_status = "failed"
        r.error = str(exc)[:500]
        db.commit()
        raise


def _apply_to_profile(db: Session, r: Resume, a) -> None:  # noqa: ANN001
    profile = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == r.candidate_id)).scalar_one()
    # Resume data fills empty profile fields; it never overwrites what the candidate entered manually.
    for field, value in (("education", [e.model_dump() for e in a.education]),
                         ("experience", [e.model_dump() for e in a.experience]),
                         ("projects", [p.model_dump() for p in a.projects]),
                         ("technologies", a.technologies), ("certifications", a.certifications),
                         ("achievements", a.achievements)):
        if not getattr(profile, field):
            setattr(profile, field, value)
    if not profile.technical_skills:
        profile.technical_skills = [s.skill for s in a.technical_skills]
    if not profile.non_technical_skills:
        profile.non_technical_skills = [s.skill for s in a.non_technical_skills]
    if not profile.summary and a.summary:
        profile.summary = a.summary
    # Resume-sourced skill evidence (replaced on each new resume version)
    db.query(CandidateSkill).filter(CandidateSkill.candidate_id == r.candidate_id, CandidateSkill.source == "resume").delete()
    seen = set()
    for s in [*a.technical_skills, *a.non_technical_skills]:
        key = normalize_key(s.skill)
        if key in seen:
            continue
        seen.add(key)
        db.add(CandidateSkill(candidate_id=r.candidate_id, institute_id=r.institute_id, skill=s.skill, skill_key=key,
                              proficiency=s.estimated_level, source="resume", confidence=s.confidence,
                              evidence=[{"quote": s.evidence, "resume_id": str(r.id), "resume_version": r.version}]))
