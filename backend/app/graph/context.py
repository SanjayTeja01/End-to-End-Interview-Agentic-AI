"""Loads the four memory layers into graph state at interview initialisation."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import readiness as readiness_domain
from app.domain import rubric
from app.models import (
    CandidateProfile,
    CandidateSkill,
    Interview,
    InterviewHistory,
    InterviewSession,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    Resume,
    User,
)
from app.services.skill_gaps import approved_requirements, compute_and_store


def load_context(db: Session, session_id: uuid.UUID) -> dict:
    session = db.get(InterviewSession, session_id)
    interview = db.get(Interview, session.interview_id)
    candidate = db.get(User, session.candidate_id)
    inst = interview.institute_id
    assert candidate.institute_id == inst == session.institute_id, "tenant mismatch"

    profile = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == candidate.id)).scalar_one_or_none()
    resume = db.execute(select(Resume).where(Resume.candidate_id == candidate.id, Resume.is_current.is_(True),
                                             Resume.processing_status == "completed")).scalar_one_or_none()
    reqs = approved_requirements(db, interview)
    gaps = compute_and_store(db, candidate_id=candidate.id, interview=interview)
    history_rows = list(db.execute(
        select(InterviewHistory).where(InterviewHistory.candidate_id == candidate.id, InterviewHistory.institute_id == inst)
        .order_by(InterviewHistory.completed_at.desc()).limit(5)).scalars())
    resume_keys = {k for (k,) in db.execute(select(CandidateSkill.skill_key).where(
        CandidateSkill.candidate_id == candidate.id, CandidateSkill.source == "resume"))}
    indexed = db.execute(select(func.count()).select_from(KnowledgeDocumentVersion).join(
        KnowledgeDocument, KnowledgeDocument.id == KnowledgeDocumentVersion.document_id).where(
        KnowledgeDocument.institute_id == inst, KnowledgeDocument.status == "active",
        KnowledgeDocumentVersion.indexing_status == "completed")).scalar_one()
    behavioral_docs = db.execute(select(func.count()).select_from(KnowledgeDocument).where(
        KnowledgeDocument.institute_id == inst, KnowledgeDocument.status == "active",
        KnowledgeDocument.document_type.in_(["interview_guideline", "evaluation_guideline"]))).scalar_one()

    weak_hist: list[str] = []
    strong_hist: list[str] = []
    for h in history_rows:
        weak_hist += [t for t in h.weak_topics if t not in weak_hist]
        strong_hist += [t for t in h.strong_topics if t not in strong_hist and t not in weak_hist]

    eval_cfg = interview.evaluation_config or {}
    read_cfg = interview.readiness_config or {}
    inst_settings = candidate.institution.settings if candidate.institution else {}
    return {
        "interview_id": str(interview.id), "institution_id": str(inst), "candidate_id": str(candidate.id),
        "user_id": str(candidate.id), "candidate_name": candidate.full_name, "target_role": interview.target_role,
        "role_id": str(interview.role_id),
        "candidate_profile": {
            "headline": profile.headline if profile else None,
            "target_roles": profile.target_roles if profile else [],
            "technical_skills": profile.technical_skills if profile else [],
            "technologies": profile.technologies if profile else [],
        },
        "resume_data": {"projects": (resume.analysis or {}).get("projects", [])[:5] if resume else [],
                        "experience": (resume.analysis or {}).get("experience", [])[:5] if resume else [],
                        "summary": (resume.analysis or {}).get("summary") if resume else None},
        "resume_skill_keys": sorted(resume_keys),
        "required_skills": [{"skill": r.skill, "skill_key": r.skill_key, "required_level": r.required_level,
                             "importance_weight": r.importance_weight, "topics": r.topics,
                             "question_categories": r.question_categories} for r in reqs],
        "role_requirements": {"role": interview.target_role, "job_description": interview.job_description[:4000]},
        "skill_gaps": gaps,
        "interview_config": {
            "name": interview.name, "interview_type": interview.interview_type,
            "question_count": interview.question_count, "duration_minutes": interview.duration_minutes,
            "initial_difficulty": interview.initial_difficulty, "adaptive_mode": interview.adaptive_mode,
            "rubric_weights": rubric.weights_for(interview.interview_type, eval_cfg.get("rubric_weights")),
            "readiness_weights": read_cfg.get("weights") or inst_settings.get("readiness_weights")
                                 or readiness_domain.DEFAULT_WEIGHTS,
            "knowledge_document_ids": [str(d) for d in interview.knowledge_document_ids or []],
            "record_media": interview.record_media,
        },
        "knowledge_available": indexed > 0,
        "has_behavioral_guidelines": behavioral_docs > 0,
        "interview_history": [{"session_id": str(h.session_id), "role_name": h.role_name, "overall_score": h.overall_score,
                               "weak_topics": h.weak_topics, "strong_topics": h.strong_topics} for h in history_rows],
        "historical_weak_topics": weak_hist[:10],
        "historical_strong_topics": strong_hist[:10],
    }
