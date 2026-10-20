from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORM


class EvaluationOut(ORM):
    id: uuid.UUID
    question_id: uuid.UUID
    topic: str | None
    skill: str | None
    difficulty: str
    technical_correctness: float
    relevance: float
    completeness: float
    clarity: float
    depth: float
    communication: float
    overall_score: float
    confidence: float
    band: str
    strengths: list
    weaknesses: list
    missing_concepts: list
    improvement_actions: list
    suggested_answer_structure: str | None
    practice_topics: list
    next_question_reason: str | None
    evidence: dict
    rubric_version: str
    created_at: datetime


class ResultOut(BaseModel):
    session_id: uuid.UUID
    interview_id: uuid.UUID
    status: str
    overall_score: float | None
    performance: dict | None
    readiness: dict | None
    recommendations: list[dict]
    report_id: uuid.UUID | None


class ReportOut(ORM):
    id: uuid.UUID
    session_id: uuid.UUID
    interview_id: uuid.UUID
    candidate_id: uuid.UUID
    version: int
    content: dict
    export_status: str
    created_at: datetime
    download_url: str | None = None


class RecommendationOut(ORM):
    id: uuid.UUID
    area: str
    area_type: str
    recommendation: str
    reason: str
    evidence: dict
    priority: float
    status: str
    session_id: uuid.UUID | None
    created_at: datetime
