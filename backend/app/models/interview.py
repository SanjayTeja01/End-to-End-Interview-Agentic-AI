from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, Timestamps, UUIDPk, utcnow, UTCDateTime


class Interview(UUIDPk, Timestamps, Base):
    __tablename__ = "interviews"

    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_role: Mapped[str] = mapped_column(String(160), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    start_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    interview_type: Mapped[str] = mapped_column(String(20), nullable=False, default="technical")
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    initial_difficulty: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    adaptive_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    evaluation_config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    readiness_config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    eligibility_config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    knowledge_document_ids: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    record_media: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    skill_approval_state: Mapped[str] = mapped_column(String(20), nullable=False, default="not_required")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class InterviewCandidate(UUIDPk, Timestamps, Base):
    __tablename__ = "interview_candidates"
    __table_args__ = (UniqueConstraint("interview_id", "candidate_id", name="uq_interview_candidate"),)

    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(20), nullable=False, default="eligible")
    eligibility_reason: Mapped[str | None] = mapped_column(Text)
    match_score: Mapped[float | None] = mapped_column(Float)
    participation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class InterviewSession(UUIDPk, Timestamps, Base):
    __tablename__ = "interview_sessions"
    # One attempt per candidate per interview; reconnects resume the same session.
    __table_args__ = (UniqueConstraint("interview_id", "candidate_id", name="uq_session_interview_candidate"),)

    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="initializing", index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    current_question_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL", use_alter=True))
    current_topic: Mapped[str | None] = mapped_column(String(160))
    current_difficulty: Mapped[str | None] = mapped_column(String(10))
    question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Serialisable LangGraph state snapshot (object references only — never binaries)
    state: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    connection: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    termination_reason: Mapped[str | None] = mapped_column(String(64))
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    interview: Mapped[Interview] = relationship()


class Question(UUIDPk, Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_question_sequence"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    spoken_text: Mapped[str | None] = mapped_column(Text)  # includes greeting/transition
    topic: Mapped[str | None] = mapped_column(String(160))
    skill: Mapped[str | None] = mapped_column(String(120))
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    context_meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    tts_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    asked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Answer(UUIDPk, Timestamps, Base):
    __tablename__ = "answers"

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), unique=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    audio_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    video_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
