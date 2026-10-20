"""Interview Planning Agent — deterministic coverage plan from role, resume, gaps and history."""
from __future__ import annotations

from app.agents.base import Agent
from app.domain.planning import build_plan


class InterviewPlanningAgent(Agent):
    name = "interview_planning"

    def plan(self, state: dict) -> dict:
        cfg = state["interview_config"]
        plan = build_plan(
            interview_type=cfg["interview_type"], question_count=cfg["question_count"],
            role_skills=state["required_skills"], skill_gaps=state.get("skill_gaps", []),
            resume_projects=(state.get("resume_data") or {}).get("projects", []),
            historical_weak_topics=state.get("historical_weak_topics", []),
            historical_strong_topics=state.get("historical_strong_topics", []),
        )
        items = [p.__dict__ for p in plan]
        rationale = (f"{len(items)} topics planned for {cfg['question_count']} questions "
                     f"({cfg['interview_type']}, start {cfg['initial_difficulty']}). "
                     f"Historical weak topics prioritised: {', '.join(state.get('historical_weak_topics', [])[:3]) or 'none'}.")
        return {"plan": items, "plan_rationale": rationale}
