from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    id: uuid.UUID
    sequence: int
    text: str
    spoken_text: str | None
    topic: str | None
    difficulty: str
    question_type: str
    tts_url: str | None = None


class TurnOut(BaseModel):
    """What the server is doing with the answer to the current question."""
    answer_id: uuid.UUID
    status: str  # received | transcribing | transcribed | evaluating | evaluated | evaluation_failed | failed
    phase: str  # transcribing | evaluating | choosing_next | evaluation_failed | failed
    attempts: int = 0
    retry_allowed: bool = False
    error: str | None = None


class SessionStateOut(BaseModel):
    session_id: uuid.UUID
    interview_id: uuid.UUID
    status: str
    question_index: int
    question_count: int
    progress: float
    current_topic: str | None
    current_difficulty: str | None
    started_at: datetime | None
    duration_minutes: int
    elapsed_seconds: float
    current_question: QuestionOut | None
    awaiting: str  # answer | processing | none
    turn: TurnOut | None = None
    ice_servers: list[str]
    record_media: bool


class TextAnswerIn(BaseModel):
    """Fallback when speech capture fails on the client; voice is the primary path."""
    question_id: uuid.UUID
    transcript: str = Field(min_length=1, max_length=20000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AnswerAccepted(BaseModel):
    answer_id: uuid.UUID
    status: str
    duplicate: bool = False


class CompleteIn(BaseModel):
    reason: str = Field(default="ended_by_candidate", max_length=64)
