"""String enums persisted as VARCHAR. Kept in one place so API, DB and UI agree."""
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    INSTITUTION_ADMIN = "institution_admin"
    INSTITUTION_STAFF = "institution_staff"
    STUDENT = "student"


INSTITUTION_ROLES = {UserRole.INSTITUTION_ADMIN, UserRole.INSTITUTION_STAFF}


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class InterviewType(StrEnum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    MIXED = "mixed"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class InterviewStatus(StrEnum):
    DRAFT = "draft"
    REQUIREMENTS_PREPARED = "requirements_prepared"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class SkillApprovalState(StrEnum):
    NOT_REQUIRED = "not_required"
    GENERATING = "generating"
    PENDING = "pending"
    APPROVED = "approved"


class SkillSource(StrEnum):
    INSTITUTION = "institution"
    AI_INFERRED = "ai_inferred"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    ASSIGNED = "assigned"
    INELIGIBLE = "ineligible"
    REVOKED = "revoked"


class ParticipationStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SessionStatus(StrEnum):
    INITIALIZING = "initializing"
    IN_PROGRESS = "in_progress"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    FAILED = "failed"


class AnswerStatus(StrEnum):
    RECEIVED = "received"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    FAILED = "failed"


class QuestionType(StrEnum):
    GREETING = "greeting"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    RESUME = "resume"
    FOLLOW_UP = "follow_up"
    CLOSING = "closing"


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(StrEnum):
    RESUME = "resume"
    KNOWLEDGE = "knowledge"
    AUDIO = "audio"
    VIDEO = "video"
    TTS = "tts"
    REPORT = "report"


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"
