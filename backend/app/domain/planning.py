"""Deterministic interview coverage planning (the Planning Agent may enrich topic wording only)."""
from __future__ import annotations

from app.domain.adaptive import PlanItem
from app.domain.text import normalize_key


def build_plan(*, interview_type: str, question_count: int, role_skills: list[dict], skill_gaps: list[dict],
               resume_projects: list[dict], historical_weak_topics: list[str], historical_strong_topics: list[str]) -> list[PlanItem]:
    """Produce a prioritised list of topics.

    role_skills: [{skill, skill_key, importance_weight, topics: [..]}]
    skill_gaps: [{skill_key, priority}]
    """
    gap_priority = {g["skill_key"]: float(g.get("priority", 0)) for g in skill_gaps}
    weak_hist = {normalize_key(t) for t in historical_weak_topics}
    strong_hist = {normalize_key(t) for t in historical_strong_topics}
    items: dict[str, PlanItem] = {}

    def add(item: PlanItem) -> None:
        key = normalize_key(item.topic)
        if key in items:
            items[key].priority = max(items[key].priority, item.priority)
        else:
            items[key] = item

    if interview_type in ("technical", "mixed"):
        for rs in role_skills:
            topics = rs.get("topics") or [rs["skill"]]
            base = float(rs.get("importance_weight", 1.0))
            gap = gap_priority.get(rs["skill_key"], 0.0)
            for i, topic in enumerate(topics[:3]):
                key = normalize_key(topic)
                prio = base + 0.5 * gap - 0.05 * i
                if key in weak_hist:
                    prio += 0.6  # continuous adaptation: revisit historical weaknesses
                if key in strong_hist:
                    prio -= 0.3  # reduce repetition of demonstrated strengths
                add(PlanItem(topic=topic, skill=rs["skill"], category="technical", priority=round(prio, 3),
                             source="history" if key in weak_hist else "role"))

    for proj in resume_projects[:2]:
        name = proj.get("name") or proj.get("title")
        if name:
            add(PlanItem(topic=f"Project: {name}", skill=(proj.get("technologies") or [None])[0], category="resume",
                         priority=0.75, source="resume"))

    if interview_type in ("behavioral", "mixed"):
        for i, topic in enumerate(("Teamwork and collaboration", "Handling challenges and failure",
                                   "Ownership and decision making", "Communication with stakeholders")):
            add(PlanItem(topic=topic, skill=None, category="behavioral",
                         priority=(0.9 if interview_type == "behavioral" else 0.55) - 0.05 * i, source="behavioral"))

    plan = sorted(items.values(), key=lambda p: (-p.priority, p.topic))
    # Allow follow-ups only when the question budget permits.
    per_topic = 3 if question_count >= 2 * max(1, len(plan)) else 2
    for p in plan:
        p.max_questions = per_topic
    # Keep the plan proportional to the question budget, but always cover at least the top topics.
    return plan[: max(3, question_count)]
