from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class Education(BaseModel):
    institution: str
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    grade: str | None = None


class Experience(BaseModel):
    organization: str
    title: str | None = None
    start: str | None = None
    end: str | None = None
    highlights: list[str] = []


class Project(BaseModel):
    name: str
    description: str | None = None
    technologies: list[str] = []
    highlights: list[str] = []


class ProfileIn(BaseModel):
    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    education: list[Education] | None = None
    experience: list[Experience] | None = None
    projects: list[Project] | None = None
    technical_skills: list[str] | None = None
    non_technical_skills: list[str] | None = None
    technologies: list[str] | None = None
    certifications: list[str] | None = None
    achievements: list[str] | None = None
    target_roles: list[str] | None = Field(default=None, max_length=10)
    preferences: dict | None = None


class ProfileOut(ORM):
    user_id: uuid.UUID
    headline: str | None
    summary: str | None
    education: list
    experience: list
    projects: list
    technical_skills: list
    non_technical_skills: list
    technologies: list
    certifications: list
    achievements: list
    target_roles: list
    preferences: dict
    updated_at: datetime


class CandidateSkillOut(ORM):
    skill: str
    proficiency: int
    source: str
    confidence: float
    evidence: list


class SkillGapOut(ORM):
    skill: str
    required_level: int
    candidate_level: float
    gap: float
    priority: float
    evidence: list
    interview_id: uuid.UUID | None
    role_id: uuid.UUID


class ResumeOut(ORM):
    id: uuid.UUID
    candidate_id: uuid.UUID
    version: int
    is_current: bool
    processing_status: str
    extraction_meta: dict
    error: str | None
    created_at: datetime


class ResumeAnalysisOut(ResumeOut):
    sections: dict
    analysis: dict
