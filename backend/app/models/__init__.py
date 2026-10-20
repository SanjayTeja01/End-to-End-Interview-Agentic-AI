"""Import every model so Base.metadata is complete (Alembic, tests)."""
from app.models.base import Base
from app.models.identity import CandidateProfile, FileObject, Institution, Job, User
from app.models.interview import Answer, Interview, InterviewCandidate, InterviewSession, Question
from app.models.results import (
    Evaluation,
    InterviewHistory,
    InterviewRecommendation,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    Performance,
    Readiness,
    Report,
)
from app.models.skills import CandidateSkill, Resume, Role, RoleSkill, SkillGap

__all__ = [
    "Base", "Institution", "User", "CandidateProfile", "FileObject", "Job", "Resume", "CandidateSkill", "Role",
    "RoleSkill", "SkillGap", "Interview", "InterviewCandidate", "InterviewSession", "Question", "Answer",
    "Evaluation", "Performance", "Readiness", "Report", "InterviewHistory", "InterviewRecommendation",
    "KnowledgeDocument", "KnowledgeDocumentVersion",
]
