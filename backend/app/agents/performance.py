"""Performance Agent — aggregates evaluations (current session + history) deterministically."""
from __future__ import annotations

from app.agents.base import Agent
from app.domain import performance


class PerformanceAgent(Agent):
    name = "performance"

    def session_performance(self, evaluations: list[dict]) -> dict:
        return performance.aggregate(evaluations)

    def history_trend(self, history: list[dict]) -> dict:
        pts = [(h.get("interview_name") or h.get("role_name", ""), float(h["overall_score"])) for h in history]
        return performance.trend(pts)
