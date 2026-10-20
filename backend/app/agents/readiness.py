"""Readiness Agent — evidence-weighted readiness (never a hiring guarantee)."""
from __future__ import annotations

from app.agents.base import Agent
from app.domain import readiness


class ReadinessAgent(Agent):
    name = "readiness"

    def assess(self, evaluations: list[dict], *, required_skills: list[dict], resume_skill_keys: set[str],
               weights: dict | None) -> dict:
        coverage = None
        if required_skills:
            covered = sum(1 for s in required_skills if s["skill_key"] in resume_skill_keys)
            coverage = covered / len(required_skills)
        return readiness.compute(evaluations, resume_skill_coverage=coverage, weights=weights)
