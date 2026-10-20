"""Pydantic contracts for every LLM-produced structure. Nothing unvalidated reaches the database."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _clip(v: str, n: int) -> str:
    return v.strip()[:n]


# ---------- Resume Analyzer ----------
class EvidencedSkill(BaseModel):
    skill: str = Field(max_length=120)
    estimated_level: int = Field(ge=0, le=5, description="0-5 proficiency suggested by the resume text only")
    evidence: str = Field(max_length=400, description="Short verbatim quote from the resume supporting the skill")
    confidence: float = Field(ge=0, le=1)


class ResumeEducation(BaseModel):
    institution: str = Field(max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, max_length=40)
    end: str | None = Field(default=None, max_length=40)
    grade: str | None = Field(default=None, max_length=60)


class ResumeExperience(BaseModel):
    organization: str = Field(max_length=200)
    title: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, max_length=40)
    end: str | None = Field(default=None, max_length=40)
    highlights: list[str] = Field(default_factory=list, max_length=10)


class ResumeProject(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    technologies: list[str] = Field(default_factory=list, max_length=20)
    highlights: list[str] = Field(default_factory=list, max_length=10)


class RoleEvidence(BaseModel):
    role: str = Field(max_length=160)
    evidence: str = Field(max_length=400)


class ResumeAnalysis(BaseModel):
    education: list[ResumeEducation] = Field(default_factory=list, max_length=10)
    experience: list[ResumeExperience] = Field(default_factory=list, max_length=20)
    projects: list[ResumeProject] = Field(default_factory=list, max_length=20)
    technical_skills: list[EvidencedSkill] = Field(default_factory=list, max_length=60)
    non_technical_skills: list[EvidencedSkill] = Field(default_factory=list, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=60)
    certifications: list[str] = Field(default_factory=list, max_length=30)
    achievements: list[str] = Field(default_factory=list, max_length=30)
    role_evidence: list[RoleEvidence] = Field(default_factory=list, max_length=20)
    summary: str | None = Field(default=None, max_length=1200)


# ---------- Role & Skill ----------
class ProposedSkill(BaseModel):
    skill: str = Field(max_length=120)
    required_level: int = Field(ge=0, le=5)
    importance: int = Field(ge=1, le=5, description="1 = nice to have, 5 = critical")
    topics: list[str] = Field(default_factory=list, max_length=6)
    question_categories: list[str] = Field(default_factory=list, max_length=6)
    rationale: str = Field(max_length=500)


class RoleRequirements(BaseModel):
    skills: list[ProposedSkill] = Field(min_length=1, max_length=20)


# ---------- Adaptive Interview ----------
class GeneratedQuestion(BaseModel):
    question: str = Field(min_length=10, max_length=700, description="Exactly one interview question")
    spoken_transition: str = Field(default="", max_length=300, description="Short natural lead-in, no feedback on scores")
    expected_points: list[str] = Field(default_factory=list, max_length=8,
                                       description="Key points a strong answer would cover (used for evaluation)")

    @field_validator("question")
    @classmethod
    def _single(cls, v: str) -> str:
        v = v.strip()
        if v.count("?") > 2:
            raise ValueError("ask one question at a time")
        return v


# ---------- Answer Evaluation ----------
class EvidencePoint(BaseModel):
    point: str = Field(max_length=300)
    evidence_quote: str = Field(default="", max_length=300, description="Verbatim quote from the candidate answer")


class AnswerAssessment(BaseModel):
    technical_correctness: float = Field(ge=0, le=10)
    relevance: float = Field(ge=0, le=10)
    completeness: float = Field(ge=0, le=10)
    clarity: float = Field(ge=0, le=10)
    depth: float = Field(ge=0, le=10)
    communication: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1, description="Confidence in this assessment given the evidence")
    strengths: list[EvidencePoint] = Field(default_factory=list, max_length=6)
    weaknesses: list[EvidencePoint] = Field(default_factory=list, max_length=6)
    missing_concepts: list[str] = Field(default_factory=list, max_length=8)
    improvement_actions: list[str] = Field(default_factory=list, max_length=6)
    suggested_answer_structure: str = Field(default="", max_length=800)
    practice_topics: list[str] = Field(default_factory=list, max_length=6)
    rationale: str = Field(default="", max_length=600, description="Concise evidence-based summary, not chain-of-thought")


# ---------- Report ----------
class ReportNarrative(BaseModel):
    summary: str = Field(max_length=1500)
    final_assessment: str = Field(max_length=800)
