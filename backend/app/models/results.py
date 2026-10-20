from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, UUIDPk, utcnow, UTCDateTime


class Evaluation(UUIDPk, Base):
    __tablename__ = "evaluations"

    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), unique=True, nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(160))
    skill: Mapped[str | None] = mapped_column(String(120))
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    # Criterion scores on a 0..10 scale
    technical_correctness: Mapped[float] = mapped_column(Float, nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    completeness: Mapped[float] = mapped_column(Float, nullable=False)
    clarity: Mapped[float] = mapped_column(Float, nullable=False)
    depth: Mapped[float] = mapped_column(Float, nullable=False)
    communication: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0..100, computed deterministically
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0..1
    band: Mapped[str] = mapped_column(String(10), nullable=False)  # strong | average | weak
    strengths: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    weaknesses: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    missing_concepts: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    improvement_actions: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    suggested_answer_structure: Mapped[str | None] = mapped_column(Text)
    practice_topics: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    next_question_reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    rubric_weights: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Performance(UUIDPk, Base):
    """Snapshot derived from evaluations when a session completes (keeps historical reports reproducible)."""

    __tablename__ = "performance"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(160), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    criterion_scores: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    topic_performance: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    skill_performance: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    difficulty_progression: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    method_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Readiness(UUIDPk, Base):
    __tablename__ = "readiness"

    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    role_name: Mapped[str] = mapped_column(String(160), nullable=False)
    components: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    overall: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    weights: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    method_version: Mapped[str] = mapped_column(String(20), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Report(UUIDPk, Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("session_id", "version", name="uq_report_session_version"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    export_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class InterviewHistory(UUIDPk, Base):
    """Compact per-session history consumed by future adaptive interviews (historical memory)."""

    __tablename__ = "interview_history"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(160), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    weak_topics: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    strong_topics: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    difficulty_responses: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    question_summaries: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    repeated_mistakes: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class InterviewRecommendation(UUIDPk, Base):
    __tablename__ = "interview_recommendations"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    area: Mapped[str] = mapped_column(String(160), nullable=False)
    area_type: Mapped[str] = mapped_column(String(20), nullable=False)  # skill | topic | criterion | resume | communication
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class KnowledgeDocument(UUIDPk, Base):
    __tablename__ = "knowledge_documents"

    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)  # job_description | guideline | question_bank | technical | evaluation_guideline | other
    role: Mapped[str | None] = mapped_column(String(160))
    topic: Mapped[str | None] = mapped_column(String(160))
    skill: Mapped[str | None] = mapped_column(String(120))
    difficulty: Mapped[str | None] = mapped_column(String(10))
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class KnowledgeDocumentVersion(UUIDPk, Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_doc_version"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    indexing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedding_version: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
