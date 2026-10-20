"""Answer-evaluation rubric. The LLM scores each criterion; the final score is computed here, deterministically."""
from __future__ import annotations

from dataclasses import dataclass

RUBRIC_VERSION = "rubric-v1"
CRITERIA = ("technical_correctness", "relevance", "completeness", "clarity", "depth", "communication")

DEFAULT_WEIGHTS: dict[str, float] = {
    "technical_correctness": 0.30,
    "relevance": 0.20,
    "completeness": 0.20,
    "clarity": 0.15,
    "depth": 0.10,
    "communication": 0.05,
}

# Behavioral interviews value structure and communication more than technical correctness.
BEHAVIORAL_WEIGHTS: dict[str, float] = {
    "technical_correctness": 0.10,
    "relevance": 0.25,
    "completeness": 0.20,
    "clarity": 0.20,
    "depth": 0.10,
    "communication": 0.15,
}

STRONG_THRESHOLD = 75.0
WEAK_THRESHOLD = 50.0


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    missing = set(CRITERIA) - set(weights)
    extra = set(weights) - set(CRITERIA)
    if missing or extra:
        raise ValueError(f"Rubric weights must cover exactly {CRITERIA}; missing={missing}, extra={extra}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("Rubric weights must be non-negative")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Rubric weights must sum to 1.0 (got {total:.4f})")
    return dict(weights)


def weights_for(interview_type: str, override: dict[str, float] | None = None) -> dict[str, float]:
    if override:
        return validate_weights(override)
    return dict(BEHAVIORAL_WEIGHTS if interview_type == "behavioral" else DEFAULT_WEIGHTS)


@dataclass(frozen=True)
class ScoredAnswer:
    overall: float  # 0..100
    band: str  # strong | average | weak


def compute_final_score(criterion_scores: dict[str, float], weights: dict[str, float]) -> ScoredAnswer:
    """FinalScore = Σ weight × criterion. Criteria are 0..10; result is scaled to 0..100."""
    for c in CRITERIA:
        v = criterion_scores.get(c)
        if v is None or not 0 <= float(v) <= 10:
            raise ValueError(f"criterion {c} must be within 0..10 (got {v!r})")
    raw = sum(weights[c] * float(criterion_scores[c]) for c in CRITERIA)
    overall = round(raw * 10, 2)
    return ScoredAnswer(overall=overall, band=band_for(overall))


def band_for(score: float) -> str:
    if score >= STRONG_THRESHOLD:
        return "strong"
    if score < WEAK_THRESHOLD:
        return "weak"
    return "average"
