"""Report Agent — assembles the final structured report; LLM writes only a short narrative."""
from __future__ import annotations

from app.agents.base import SYSTEM_GUARDRAILS, Agent
from app.agents.schemas import ReportNarrative
from app.domain.readiness import DISCLAIMER

REPORT_VERSION = "report-v1"


class ReportAgent(Agent):
    name = "report"

    def build(self, *, state: dict, questions: list[dict], performance: dict, readiness: dict,
              recommendations: list[dict]) -> dict:
        strengths, weaknesses, missing = [], [], []
        for q in questions:
            ev = q.get("evaluation") or {}
            strengths += [s["point"] for s in ev.get("strengths", [])]
            weaknesses += [w["point"] for w in ev.get("weaknesses", [])]
            missing += ev.get("missing_concepts", [])
        content = {
            "report_version": REPORT_VERSION,
            "candidate": {"id": state["candidate_id"], "name": state.get("candidate_name")},
            "interview": {"id": state["interview_id"], "name": state["interview_config"]["name"],
                          "type": state["interview_config"]["interview_type"], "target_role": state["target_role"]},
            "overall_score": performance.get("overall_score"),
            "criterion_scores": performance.get("criterion_scores"),
            "topic_performance": performance.get("topic_performance"),
            "skill_performance": performance.get("skill_performance"),
            "adaptive_progression": performance.get("difficulty_progression"),
            "strengths": _dedupe(strengths)[:8],
            "weaknesses": _dedupe(weaknesses)[:8],
            "missing_concepts": _dedupe(missing)[:10],
            "weak_topics": state.get("weak_topics", []),
            "strong_topics": state.get("strong_topics", []),
            "readiness": readiness,
            "recommendations": recommendations,
            "questions": [{
                "sequence": q["sequence"], "question": q["text"], "topic": q.get("topic"), "difficulty": q["difficulty"],
                "answer_excerpt": (q.get("transcript") or "")[:600],
                "score": (q.get("evaluation") or {}).get("overall_score"),
                "next_question_reason": (q.get("evaluation") or {}).get("next_question_reason"),
            } for q in questions],
            "stop_reason": state.get("stop_reason"),
            "disclaimer": DISCLAIMER,
        }
        content.update(self._narrative(content))
        return content

    def _narrative(self, content: dict) -> dict:
        prompt = (
            "Write a concise, professional interview summary (3-5 sentences) and a one-paragraph final assessment for the "
            "institution and candidate, using ONLY these structured results. Do not mention hiring guarantees, personality "
            "or appearance.\n\n"
            f"Role: {content['interview']['target_role']}\nOverall: {content['overall_score']}\n"
            f"Criteria: {content['criterion_scores']}\nTopics: {content['topic_performance']}\n"
            f"Strengths: {content['strengths']}\nWeaknesses: {content['weaknesses']}\n"
            f"Readiness: {content['readiness'].get('overall')} ({content['readiness'].get('level')})"
        )
        try:
            n = self.llm.generate_structured(system=SYSTEM_GUARDRAILS, prompt=prompt, schema=ReportNarrative,
                                             temperature=0.3, purpose="report_narrative")
            return {"summary": n.summary, "final_assessment": n.final_assessment, "narrative_source": "llm"}
        except Exception:  # noqa: BLE001 — the report must still be produced
            ws = ", ".join(content["weak_topics"][:3]) or "none identified"
            ss = ", ".join(content["strong_topics"][:3]) or "none identified"
            return {
                "summary": f"Overall score {content['overall_score']}/100 across {len(content['questions'])} questions. "
                           f"Strong topics: {ss}. Topics needing work: {ws}.",
                "final_assessment": f"Readiness {content['readiness'].get('overall')}/100 "
                                    f"({str(content['readiness'].get('level')).replace('_', ' ')}). {DISCLAIMER}",
                "narrative_source": "template",
            }


def _dedupe(xs: list[str]) -> list[str]:
    seen, out = set(), []
    for x in xs:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out
