"""Performance aggregation derived purely from stored evaluations (single source of truth)."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from app.domain.rubric import CRITERIA

PERFORMANCE_VERSION = "perf-v1"


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def aggregate(evaluations: list[dict]) -> dict:
    """evaluations: dicts with overall_score, criteria (0..10), topic, skill, difficulty, sequence, category."""
    evs = sorted(evaluations, key=lambda e: e.get("sequence", 0))
    topic: dict[str, list[float]] = defaultdict(list)
    skill: dict[str, list[float]] = defaultdict(list)
    for e in evs:
        if e.get("topic"):
            topic[e["topic"]].append(e["overall_score"])
        if e.get("skill"):
            skill[e["skill"]].append(e["overall_score"])
    return {
        "overall_score": _avg([e["overall_score"] for e in evs]) or 0.0,
        "answered": len(evs),
        "criterion_scores": {c: _avg([e[c] * 10 for e in evs]) for c in CRITERIA} if evs else {},
        "topic_performance": {t: {"average": _avg(v), "count": len(v)} for t, v in topic.items()},
        "skill_performance": {s: {"average": _avg(v), "count": len(v)} for s, v in skill.items()},
        "difficulty_progression": [
            {"sequence": e.get("sequence"), "difficulty": e["difficulty"], "score": e["overall_score"], "topic": e.get("topic")}
            for e in evs
        ],
        "method_version": PERFORMANCE_VERSION,
    }


def trend(points: list[tuple[str, float]]) -> dict:
    """Simple trend over (label, score) history: slope via first/last and delta vs. previous."""
    if not points:
        return {"points": [], "delta": None, "direction": "none"}
    delta = round(points[-1][1] - points[-2][1], 2) if len(points) > 1 else None
    direction = "none" if delta is None else ("up" if delta > 2 else "down" if delta < -2 else "flat")
    return {"points": [{"label": l, "score": s} for l, s in points], "delta": delta, "direction": direction}
