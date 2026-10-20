"""Adaptive Interview Agent — words the next question within the topic/difficulty chosen by the policy."""
from __future__ import annotations

from app.agents.base import SYSTEM_GUARDRAILS, Agent
from app.agents.schemas import GeneratedQuestion
from app.domain.text import jaccard
from app.services.llm import LLMError

KIND_GUIDANCE = {
    "new_topic": "Open the topic with a clear question at the requested difficulty.",
    "follow_up_deeper": "Ask a deeper follow-up on the candidate's previous answer: reasoning, application, trade-offs or edge cases.",
    "follow_up_probe": "Ask a follow-up that probes the gaps in the previous answer at the same difficulty.",
    "follow_up_gap": "The previous answer was right but left out a key concept. Ask a follow-up that tests that "
                     "missing concept directly, without naming the answer.",
    "follow_up_clarify": "The previous answer was too vague to judge. Ask the candidate to clarify it with one "
                         "specific, concrete example or step, at the same difficulty.",
    "follow_up_foundational": "Ask a simpler, foundational question on the same topic to check core understanding.",
}
DIFFICULTY_GUIDANCE = {
    "easy": "definitions and core concepts",
    "medium": "applying concepts to a realistic scenario",
    "hard": "design decisions, trade-offs, scaling, failure modes",
}


def _repeats(text: str, previous: list[dict]) -> bool:
    return any(jaccard(text, p["text"]) > 0.75 for p in previous)


def _profile_line(state: dict) -> str:
    """Compact performance profile (a few numbers, not the whole transcript) so wording can build on it."""
    stats = state.get("topic_stats") or {}
    if not stats:
        return ""
    parts = [f"{t}: avg {sum(v['scores']) / len(v['scores']):.0f} over {len(v['scores'])}" for t, v in stats.items()
             if v.get("scores")]
    return (f"Performance so far: {'; '.join(parts)}. Weak: {', '.join(state.get('weak_topics') or []) or 'none'}. "
            f"Strong: {', '.join(state.get('strong_topics') or []) or 'none'}.")


class AdaptiveInterviewAgent(Agent):
    name = "adaptive_interview"

    def generate(self, state: dict) -> GeneratedQuestion:
        d = state["decision"]
        previous = state.get("asked_questions", [])
        last = state.get("last_turn") or {}
        resume = state.get("resume_data") or {}
        project_ctx = ""
        if d.get("category") == "resume":
            name = d["topic"].removeprefix("Project: ")
            proj = next((p for p in resume.get("projects", []) if p.get("name") == name), None)
            if proj:
                project_ctx = (f"Resume project (claims to verify, do not assume true): {proj.get('name')} — "
                               f"{proj.get('description') or ''} Technologies: {', '.join(proj.get('technologies', []))}")
        prompt = "\n".join(filter(None, [
            f"Role: {state['target_role']}. Interview type: {state['interview_config']['interview_type']}.",
            f"Question {state['interview_progress']['asked'] + 1} of {state['interview_config']['question_count']}.",
            f"Topic: {d['topic']} | Skill: {d.get('skill') or 'n/a'} | Category: {d['category']}",
            f"Difficulty: {d['difficulty']} ({DIFFICULTY_GUIDANCE[d['difficulty']]}).",
            f"Instruction: {KIND_GUIDANCE[d['kind']]}",
            project_ctx,
            f"Candidate's known weak topics from history: {', '.join(state.get('historical_weak_topics', [])[:5]) or 'none'}.",
            (f"Previous question: {last.get('question')}\nCandidate answer (transcript): {last.get('answer', '')[:2000]}\n"
             f"Evaluation summary: {last.get('summary', '')}") if d["kind"] != "new_topic" and last else "",
            f"Gaps to target: {', '.join(d['focus'])}" if d.get("focus") else "",
            _profile_line(state),
            f"Institution knowledge for grounding (use if relevant, do not quote verbatim):\n{state.get('retrieved_context') or '(none)'}",
            "Questions already asked (do not repeat or paraphrase):\n- " + "\n- ".join(q["text"] for q in previous[-12:]) if previous else "",
            "Write ONE question. Keep it under 60 words, conversational and spoken-friendly (no code blocks, no lists). "
            "spoken_transition is a brief neutral lead-in (e.g. 'Let's move on to databases.'), never praise or scores. "
            "Also list the key points a strong answer should cover.",
        ]))
        q = self.llm.generate_structured(system=SYSTEM_GUARDRAILS, prompt=prompt, schema=GeneratedQuestion,
                                         temperature=0.6, purpose="question_generation")
        if _repeats(q.question, previous):
            q = self.llm.generate_structured(system=SYSTEM_GUARDRAILS,
                                             prompt=prompt + "\n\nThe previous draft repeated an earlier question. Ask something different.",
                                             schema=GeneratedQuestion, temperature=0.8, purpose="question_generation_retry")
            if _repeats(q.question, previous):
                raise LLMError("question_generation produced a repeated question twice")  # caller uses the template
        return q

    @staticmethod
    def greeting(candidate_name: str, interview_name: str, question_count: int, duration_minutes: int) -> str:
        first = candidate_name.split()[0] if candidate_name else "there"
        return (f"Hello {first}, welcome to the {interview_name}. I'm your AI interviewer. "
                f"I'll ask about {question_count} questions over roughly {duration_minutes} minutes, one at a time. "
                "Take a moment to think, answer naturally, and press 'Done answering' when you finish. Let's begin.")

    @staticmethod
    def closing() -> str:
        return ("That concludes the interview. Thank you for your time. Your results and feedback will be available "
                "on your dashboard shortly.")
