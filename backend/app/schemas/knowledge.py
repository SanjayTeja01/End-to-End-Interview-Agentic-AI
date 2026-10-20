from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORM

DocType = Literal["job_description", "role_document", "interview_guideline", "technical", "question_bank",
                  "institution_info", "domain_info", "evaluation_guideline", "other"]


class KnowledgeVersionOut(ORM):
    id: uuid.UUID
    version: int
    checksum: str
    processing_status: str
    indexing_status: str
    chunk_count: int
    embedding_model: str | None
    embedding_version: str | None
    error: str | None
    created_at: datetime
    indexed_at: datetime | None


class KnowledgeDocumentOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    document_type: str
    role: str | None
    topic: str | None
    skill: str | None
    difficulty: str | None
    current_version: int
    status: str
    created_at: datetime
    updated_at: datetime
    latest: KnowledgeVersionOut | None = None


class KnowledgeDocumentDetail(KnowledgeDocumentOut):
    versions: list[KnowledgeVersionOut] = []


class KnowledgeUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    document_type: DocType | None = None
    role: str | None = Field(default=None, max_length=160)
    topic: str | None = Field(default=None, max_length=160)
    skill: str | None = Field(default=None, max_length=120)
    difficulty: Literal["easy", "medium", "hard"] | None = None
    status: Literal["active", "inactive"] | None = None


class RagQueryIn(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    role: str | None = None
    topic: str | None = None
    skill: str | None = None
    document_type: str | None = None
    k: int = Field(default=5, ge=1, le=20)


class RagHit(BaseModel):
    chunk_id: str
    text: str
    score: float
    doc_id: str
    source_title: str
    version: int
    metadata: dict
