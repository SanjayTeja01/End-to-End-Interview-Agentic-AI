"""Role & Skill Agent — proposes requirements from role + JD + tenant RAG context (institution approves)."""
from __future__ import annotations

from app.agents.base import SYSTEM_GUARDRAILS, Agent
from app.agents.schemas import RoleRequirements


class RoleSkillAgent(Agent):
    name = "role_skill"

    def infer(self, *, role: str, job_description: str, interview_type: str, knowledge_context: str) -> RoleRequirements:
        prompt = (
            f"Target role: {role}\nInterview type: {interview_type}\n\nJob description:\n{job_description[:12000] or '(none provided)'}\n\n"
            f"Institution knowledge (may be empty):\n{knowledge_context[:6000] or '(none)'}\n\n"
            "Propose 5-12 required skills for interviewing this role. For each give: required proficiency on a 0-5 "
            "scale (0 Missing, 1 Beginner, 2 Basic, 3 Intermediate, 4 Advanced, 5 Strong), importance 1-5, 2-4 concrete "
            "interview topics, question categories (e.g. conceptual, applied, design, debugging, behavioral) and a "
            "one-sentence rationale citing the JD or knowledge. Prefer skills explicitly required by the JD."
        )
        out = self.llm.generate_structured(system=SYSTEM_GUARDRAILS, prompt=prompt, schema=RoleRequirements,
                                           temperature=0.2, purpose="role_skill_inference")
        # De-duplicate by normalised name, keep the higher importance.
        from app.domain.text import normalize_key

        best: dict[str, object] = {}
        for s in out.skills:
            k = normalize_key(s.skill)
            if k not in best or s.importance > best[k].importance:  # type: ignore[attr-defined]
                best[k] = s
        out.skills = list(best.values())  # type: ignore[assignment]
        return out
