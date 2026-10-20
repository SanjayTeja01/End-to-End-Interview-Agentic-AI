from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk, utcnow, UTCDateTime


class Resume(UUIDPk, Timestamps, Base):
    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("candidate_id", "version", name="uq_resume_candidate_version"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(default=True, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # Extraction metadata only (char count, page count, detected sections) — the raw text stays in the worker
    extraction_meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    sections: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    analysis: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class CandidateSkill(UUIDPk, Timestamps, Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("candidate_id", "skill_key", "source", name="uq_candidate_skill_source"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_key: Mapped[str] = mapped_column(String(120), nullable=False)  # normalised
    proficiency: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..5
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # resume | interview | profile
    evidence: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)


class Role(UUIDPk, Timestamps, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("institute_id", "normalized_name", name="uq_role_institute_name"),)

    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class RoleSkill(UUIDPk, Timestamps, Base):
    """Required skill for a role. Scoped to an interview when requirements are interview-specific."""

    __tablename__ = "role_skills"
    __table_args__ = (UniqueConstraint("role_id", "interview_id", "skill_key", name="uq_role_skill"),)

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_key: Mapped[str] = mapped_column(String(120), nullable=False)
    required_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..5
    importance_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # 0..1
    topics: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    question_categories: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    rationale: Mapped[str | None] = mapped_column(Text)


class SkillGap(UUIDPk, Base):
    __tablename__ = "skill_gaps"
    __table_args__ = (UniqueConstraint("candidate_id", "role_id", "interview_id", "skill_key", name="uq_skill_gap"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_key: Mapped[str] = mapped_column(String(120), nullable=False)
    required_level: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_level: Mapped[float] = mapped_column(Float, nullable=False)
    gap: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
