from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain import readiness as readiness_domain
from app.domain import rubric
from app.schemas.common import ORM


class RequiredSkillIn(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    required_level: int = Field(ge=0, le=5)
    importance_weight: float = Field(default=1.0, ge=0, le=1)
    topics: list[str] = Field(default_factory=list, max_length=10)
    question_categories: list[str] = Field(default_factory=list, max_length=10)


class EligibilityConfig(BaseModel):
    mode: Literal["role_match", "assigned_only", "all_students"] = "role_match"
    min_similarity: float = Field(default=0.5, ge=0, le=1)
    min_semantic_similarity: float = Field(default=0.85, ge=0, le=1)


class EvaluationConfig(BaseModel):
    rubric_weights: dict[str, float] | None = None

    @field_validator("rubric_weights")
    @classmethod
    def _valid(cls, v):  # noqa: ANN001, ANN206
        return rubric.validate_weights(v) if v else v


class ReadinessConfig(BaseModel):
    weights: dict[str, float] | None = None

    @field_validator("weights")
    @classmethod
    def _valid(cls, v):  # noqa: ANN001, ANN206
        return readiness_domain.validate_weights(v) if v else v


class InterviewBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_role: str = Field(min_length=1, max_length=160)
    job_description: str = Field(default="", max_length=20000)
    duration_minutes: int = Field(default=30, ge=5, le=240)
    start_time: datetime | None = None
    end_time: datetime | None = None
    interview_type: Literal["technical", "behavioral", "mixed"] = "technical"
    question_count: int = Field(default=8, ge=1, le=50)
    initial_difficulty: Literal["easy", "medium", "hard"] = "medium"
    adaptive_mode: bool = True
    evaluation_config: EvaluationConfig = EvaluationConfig()
    readiness_config: ReadinessConfig = ReadinessConfig()
    eligibility_config: EligibilityConfig = EligibilityConfig()
    knowledge_document_ids: list[uuid.UUID] = Field(default_factory=list)
    record_media: bool = False

    @model_validator(mode="after")
    def _schedule(self):  # noqa: ANN202
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class InterviewCreate(InterviewBase):
    required_skills: list[RequiredSkillIn] = Field(default_factory=list, max_length=40)
    infer_skills: bool = True  # when no skills given, the Role & Skill Agent proposes requirements


class InterviewUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    job_description: str | None = Field(default=None, max_length=20000)
    duration_minutes: int | None = Field(default=None, ge=5, le=240)
    start_time: datetime | None = None
    end_time: datetime | None = None
    interview_type: Literal["technical", "behavioral", "mixed"] | None = None
    question_count: int | None = Field(default=None, ge=1, le=50)
    initial_difficulty: Literal["easy", "medium", "hard"] | None = None
    adaptive_mode: bool | None = None
    evaluation_config: EvaluationConfig | None = None
    readiness_config: ReadinessConfig | None = None
    eligibility_config: EligibilityConfig | None = None
    knowledge_document_ids: list[uuid.UUID] | None = None
    record_media: bool | None = None


class RoleSkillOut(ORM):
    id: uuid.UUID
    skill: str
    required_level: int
    importance_weight: float
    topics: list
    question_categories: list
    source: str
    approval_status: str
    rationale: str | None


class SkillsReplaceIn(BaseModel):
    """Institution edit of the (AI-proposed or manual) requirements before approval."""
    skills: list[RequiredSkillIn] = Field(min_length=1, max_length=40)


class InterviewStats(BaseModel):
    candidate_count: int = 0
    participated: int = 0
    in_progress: int = 0
    completed: int = 0
    average_score: float | None = None


class InterviewOut(ORM):
    id: uuid.UUID
    name: str
    target_role: str
    role_id: uuid.UUID
    job_description: str
    duration_minutes: int
    start_time: datetime | None
    end_time: datetime | None
    interview_type: str
    question_count: int
    initial_difficulty: str
    adaptive_mode: bool
    evaluation_config: dict
    readiness_config: dict
    eligibility_config: dict
    knowledge_document_ids: list
    record_media: bool
    status: str
    effective_status: str | None = None
    skill_approval_state: str
    created_at: datetime
    updated_at: datetime
    stats: InterviewStats | None = None


class InterviewDetailOut(InterviewOut):
    skills: list[RoleSkillOut] = []


class CandidateInterviewOut(BaseModel):
    """What a student sees — no evaluation configuration or other candidates' data."""
    id: uuid.UUID
    name: str
    target_role: str
    interview_type: str
    duration_minutes: int
    question_count: int
    start_time: datetime | None
    end_time: datetime | None
    status: str
    joinable: bool
    eligibility_reason: str
    participation_status: str
    session_id: uuid.UUID | None = None


class AssignCandidatesIn(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: Literal["assign", "revoke"] = "assign"


class InterviewCandidateRow(BaseModel):
    candidate_id: uuid.UUID
    full_name: str
    email: str
    eligibility_status: str
    participation_status: str
    match_score: float | None
    session_id: uuid.UUID | None
    session_status: str | None
    score: float | None
    progress: float | None
