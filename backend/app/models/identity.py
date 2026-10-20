from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, Timestamps, UUIDPk, UTCDateTime


class Institution(UUIDPk, Timestamps, Base):
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    # Code students use to register under this institution (rotatable)
    join_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # Institution-level overrides: readiness weights, default rubric, etc.
    settings: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    institute_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    institution: Mapped[Institution | None] = relationship()
    profile: Mapped["CandidateProfile | None"] = relationship(back_populates="user", uselist=False)


class CandidateProfile(UUIDPk, Timestamps, Base):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    headline: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    education: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    experience: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    projects: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    technical_skills: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    non_technical_skills: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    technologies: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    certifications: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    achievements: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    target_roles: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")


class FileObject(UUIDPk, Timestamps, Base):
    """Metadata for a blob stored in MinIO. Postgres holds the object key, never a public URL."""

    __tablename__ = "files"
    __table_args__ = (Index("ix_files_institute_type", "institute_id", "file_type"),)

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Job(UUIDPk, Timestamps, Base):
    """Status of an asynchronous Celery job, queryable by the frontend."""

    __tablename__ = "jobs"

    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
