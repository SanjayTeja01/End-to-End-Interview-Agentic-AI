"""Readiness: converts measured interview evidence into an overall readiness estimate.

Readiness is an evidence-based indicator of interview preparedness — never a hiring guarantee.
"""
from __future__ import annotations

from statistics import mean

READINESS_VERSION = "readiness-v1"
DISCLAIMER = ("Readiness reflects performance in this interview and prior evidence only. "
              "It is not a prediction or guarantee of any hiring outcome.")

DEFAULT_WEIGHTS = {"technical": 0.35, "problem_solving": 0.20, "communication": 0.20, "behavioral": 0.15, "resume": 0.10}
_DIFFICULTY_FACTOR = {"easy": 0.9, "medium": 1.0, "hard": 1.15}


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ValueError(f"Readiness weights must cover exactly {sorted(DEFAULT_WEIGHTS)}")
    if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError("Readiness weights must be non-negative and sum to 1.0")
    return dict(weights)


def level_for(score: float) -> str:
    if score >= 80:
        return "interview_ready"
    if score >= 65:
        return "nearly_ready"
    if score >= 50:
        return "developing"
    return "needs_preparation"


def _m(xs: list[float]) -> float | None:
    return round(mean(xs), 2) if xs else None


def compute(evaluations: list[dict], *, resume_skill_coverage: float | None, weights: dict[str, float] | None = None) -> dict:
    """evaluations: dicts with category, difficulty, overall_score and 0..10 criteria.

    resume_skill_coverage: fraction 0..1 of required skills with supporting resume evidence (or None).
    """
    w = validate_weights(weights) if weights else dict(DEFAULT_WEIGHTS)
    tech = [e for e in evaluations if e.get("category") in ("technical", "resume")]
    beh = [e for e in evaluations if e.get("category") == "behavioral"]
    res_q = [e for e in evaluations if e.get("category") == "resume"]

    def capped(v: float) -> float:
        return min(100.0, v)

    components: dict[str, float | None] = {
        "technical": _m([(0.6 * e["technical_correctness"] + 0.4 * e["depth"]) * 10 for e in tech]),
        "problem_solving": _m([capped((0.5 * e["depth"] + 0.5 * e["completeness"]) * 10 * _DIFFICULTY_FACTOR.get(e["difficulty"], 1.0))
                               for e in tech]),
        "communication": _m([(0.5 * e["clarity"] + 0.5 * e["communication"]) * 10 for e in evaluations]),
        "behavioral": _m([e["overall_score"] for e in beh]),
        "resume": None,
    }
    resume_parts = []
    if res_q:
        resume_parts.append(mean(e["overall_score"] for e in res_q))
    if resume_skill_coverage is not None:
        resume_parts.append(100 * max(0.0, min(1.0, resume_skill_coverage)))
    components["resume"] = _m(resume_parts)

    present = {k: v for k, v in components.items() if v is not None}
    total_w = sum(w[k] for k in present)
    overall = round(sum(w[k] * v for k, v in present.items()) / total_w, 2) if total_w else 0.0
    return {
        "components": components,
        "overall": overall,
        "level": level_for(overall),
        "weights": w,
        "effective_weights": {k: round(w[k] / total_w, 4) for k in present} if total_w else {},
        "evidence": {
            "answers_considered": len(evaluations),
            "technical_answers": len(tech),
            "behavioral_answers": len(beh),
            "resume_skill_coverage": resume_skill_coverage,
            "excluded_components": sorted(k for k, v in components.items() if v is None),
        },
        "disclaimer": DISCLAIMER,
        "method_version": READINESS_VERSION,
    }
