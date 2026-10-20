"""Answer Evaluation Agent — rubric scoring grounded in the transcript; final score computed deterministically."""
from __future__ import annotations

import re

from app.agents.base import SYSTEM_GUARDRAILS, Agent
from app.agents.schemas import AnswerAssessment
from app.domain import rubric

MIN_WORDS = 4


def _grounded(points, transcript_low: str):  # noqa: ANN001, ANN202
    out = []
    for p in points:
        q = re.sub(r"\s+", " ", (p.evidence_quote or "").lower()).strip()
        if not q or q[:50] in transcript_low:
            out.append({"point": p.point, "evidence": p.evidence_quote or None})
    return out


class AnswerEvaluationAgent(Agent):
    name = "answer_evaluation"

    def evaluate(self, *, question: dict, transcript: str, weights: dict[str, float], role: str,
                 knowledge_context: str = "") -> dict:
        words = len(transcript.split())
        if words < MIN_WORDS:
            return self._no_answer(question, transcript, weights)
        prompt = "\n".join([
            f"Role: {role}. Question type: {question['question_type']}. Topic: {question.get('topic')}. Difficulty: {question['difficulty']}.",
            f"QUESTION: {question['text']}",
            f"KEY POINTS A STRONG ANSWER COVERS: {'; '.join(question.get('expected_points') or []) or '(not specified)'}",
            f"EVALUATION GUIDELINES / KNOWLEDGE:\n{knowledge_context[:3000] or '(none)'}",
            f"CANDIDATE ANSWER (speech transcript, may contain recognition errors):\n{transcript[:6000]}",
            "Score each criterion 0-10 using ONLY what the candidate said: technical_correctness, relevance, completeness, "
            "clarity, depth, communication (verbal structure and articulation only — never accent, voice or appearance). "
            "Do not penalise minor transcription errors. A short answer that is correct and covers the key points must "
            "not lose marks for length: judge depth by the reasoning shown, not by word count. "
            "Strengths/weaknesses must quote the answer verbatim in evidence_quote. "
            "List missing concepts, concrete improvement actions, a suggested answer structure and practice topics. "
            "confidence reflects how much evidence the answer provides (short or ambiguous answers → lower).",
        ])
        a = self.llm.generate_structured(system=SYSTEM_GUARDRAILS, prompt=prompt, schema=AnswerAssessment,
                                         temperature=0.0, purpose="answer_evaluation")
        return self._finalize(a, transcript, weights)

    def _finalize(self, a: AnswerAssessment, transcript: str, weights: dict[str, float]) -> dict:
        scores = {c: round(float(getattr(a, c)), 2) for c in rubric.CRITERIA}
        scored = rubric.compute_final_score(scores, weights)
        low = re.sub(r"\s+", " ", transcript.lower())
        return {
            **scores,
            "overall_score": scored.overall,
            "band": scored.band,
            "confidence": round(a.confidence, 2),
            "strengths": _grounded(a.strengths, low),
            "weaknesses": [{"point": w.point, "evidence": w.evidence_quote or None} for w in a.weaknesses],
            "missing_concepts": a.missing_concepts,
            "improvement_actions": a.improvement_actions,
            "suggested_answer_structure": a.suggested_answer_structure,
            "practice_topics": a.practice_topics,
            "evidence": {"summary": a.rationale, "words": len(transcript.split())},
            "rubric_weights": weights,
            "rubric_version": rubric.RUBRIC_VERSION,
        }

    @staticmethod
    def _no_answer(question: dict, transcript: str, weights: dict[str, float]) -> dict:
        scores = {c: 0.0 for c in rubric.CRITERIA}
        return {
            **scores, "overall_score": 0.0, "band": "weak", "confidence": 0.9,
            "strengths": [], "weaknesses": [{"point": "No substantive answer was given", "evidence": transcript or None}],
            "missing_concepts": [], "improvement_actions": ["Attempt an answer even if unsure — explain what you do know and how you would find out the rest."],
            "suggested_answer_structure": "State your understanding, give one example, mention a trade-off.",
            "practice_topics": [question.get("topic")] if question.get("topic") else [],
            "evidence": {"summary": "Answer too short to assess.", "words": len(transcript.split())},
            "rubric_weights": weights, "rubric_version": rubric.RUBRIC_VERSION,
        }
