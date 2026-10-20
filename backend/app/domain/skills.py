"""Skill proficiency model (0–5), gap and priority calculations."""
from __future__ import annotations

from dataclasses import dataclass, field

LEVEL_LABELS = {0: "Missing", 1: "Beginner", 2: "Basic", 3: "Intermediate", 4: "Advanced", 5: "Strong"}

# How much each evidence source is trusted when estimating a candidate's level.
# Resume claims are evidence to investigate, not proof — they carry the lowest weight.
SOURCE_WEIGHTS = {"interview": 1.0, "assessment": 0.9, "profile": 0.4, "resume": 0.5}


@dataclass
class SkillEvidence:
    source: str  # interview | assessment | profile | resume
    level: float  # 0..5
    confidence: float = 0.5  # 0..1
    note: str = ""


@dataclass
class GapResult:
    skill: str
    required_level: int
    candidate_level: float
    gap: float
    importance_weight: float
    priority: float
    evidence: list[dict] = field(default_factory=list)


def clamp_level(v: float) -> float:
    return max(0.0, min(5.0, float(v)))


def estimate_candidate_level(evidence: list[SkillEvidence]) -> float:
    """Confidence- and source-weighted average of evidence; no evidence means level 0 (Missing)."""
    num = 0.0
    den = 0.0
    for e in evidence:
        w = SOURCE_WEIGHTS.get(e.source, 0.3) * max(0.05, min(1.0, e.confidence))
        num += w * clamp_level(e.level)
        den += w
    return round(num / den, 2) if den else 0.0


def skill_gap(required_level: int, candidate_level: float) -> float:
    """Gap(skill) = RequiredLevel − CandidateLevel, floored at 0 (exceeding the requirement is not a gap)."""
    if not 0 <= required_level <= 5:
        raise ValueError("required_level must be within 0..5")
    return round(max(0.0, required_level - clamp_level(candidate_level)), 2)


def skill_priority(gap: float, importance_weight: float) -> float:
    """Priority(skill) = Gap × ImportanceWeight."""
    return round(gap * max(0.0, importance_weight), 3)


def compute_gaps(requirements: list[dict], evidence_by_skill: dict[str, list[SkillEvidence]]) -> list[GapResult]:
    """requirements: [{skill, skill_key, required_level, importance_weight}] -> gaps sorted by priority desc."""
    results: list[GapResult] = []
    for req in requirements:
        ev = evidence_by_skill.get(req["skill_key"], [])
        level = estimate_candidate_level(ev)
        gap = skill_gap(int(req["required_level"]), level)
        results.append(GapResult(
            skill=req["skill"], required_level=int(req["required_level"]), candidate_level=level, gap=gap,
            importance_weight=float(req.get("importance_weight", 1.0)),
            priority=skill_priority(gap, float(req.get("importance_weight", 1.0))),
            evidence=[{"source": e.source, "level": e.level, "confidence": e.confidence, "note": e.note} for e in ev],
        ))
    results.sort(key=lambda r: (-r.priority, r.skill))
    return results


def score_to_level(score_0_100: float) -> float:
    """Map an interview answer score to the 0..5 proficiency scale."""
    return round(clamp_level(score_0_100 / 20.0), 2)
