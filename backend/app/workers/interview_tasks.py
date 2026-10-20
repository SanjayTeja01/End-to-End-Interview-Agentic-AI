"""Role & Skill inference job (slow LLM + RAG call) for interviews without institution-provided skills."""
from __future__ import annotations

import uuid

from app.agents.rag_knowledge import RAGKnowledgeAgent
from app.agents.role_skill import RoleSkillAgent
from app.core.database import SessionLocal
from app.models import Interview
from app.services import jobs
from app.services.interviews import apply_inferred_skills
from app.services.llm import LLMConfigError
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=1, default_retry_delay=5)
def infer_requirements(self, interview_id: str, job_id: str | None = None) -> None:  # noqa: ANN001
    db = SessionLocal()
    try:
        jobs.mark(db, job_id, "processing")
        iv = db.get(Interview, uuid.UUID(interview_id))
        try:
            context, _ = RAGKnowledgeAgent().retrieve_for_requirements(
                institute_id=str(iv.institute_id), role=iv.target_role, job_description=iv.job_description,
                doc_ids=iv.knowledge_document_ids or None)
        except Exception:  # noqa: BLE001 — RAG is optional support
            context = ""
        proposals = RoleSkillAgent().infer(role=iv.target_role, job_description=iv.job_description,
                                           interview_type=iv.interview_type, knowledge_context=context)
        apply_inferred_skills(db, iv, proposals)
        db.commit()
        jobs.mark(db, job_id, "completed", result={"skills": len(proposals.skills)})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if self.request.retries < self.max_retries and not isinstance(exc, LLMConfigError):
            raise self.retry(exc=exc)
        iv = db.get(Interview, uuid.UUID(interview_id))
        if iv:
            iv.skill_approval_state = "pending"  # institution can enter skills manually
            db.commit()
        jobs.mark(db, job_id, "failed", error=str(exc))
        raise
    finally:
        db.close()
