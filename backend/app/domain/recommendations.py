"""Focused interview-improvement recommendations (not a study plan / LMS)."""
from __future__ import annotations

from collections import Counter

CRITERION_ADVICE = {
    "technical_correctness": "Double-check core definitions and verify claims before stating them; practise explaining concepts precisely.",
    "relevance": "Answer the question that was asked first, then add context — restate the question in one line before answering.",
    "completeness": "Cover the main parts of the answer (what, why, how, trade-offs) before going deep on one part.",
    "clarity": "Structure answers: one-sentence summary, two or three key points, short example.",
    "depth": "Go one level deeper — explain why a technique works, its limitations, and when you would not use it.",
    "communication": "Speak in shorter sentences, avoid filler, and signpost your structure ('first… second…').",
}

LOW_CRITERION = 55.0  # on 0..100 scale


def generate(*, topic_performance: dict, criterion_scores: dict, missing_concepts: list[str], weak_topics: list[str],
             historical_weak_topics: list[str], skill_gaps: list[dict], limit: int = 8) -> list[dict]:
    recs: list[dict] = []
    hist = set(historical_weak_topics)
    concept_counts = Counter(c.strip() for c in missing_concepts if c and c.strip())

    for topic in weak_topics:
        avg = (topic_performance.get(topic) or {}).get("average")
        repeated = topic in hist
        related = [c for c, _ in concept_counts.most_common() if c.lower() in topic.lower() or topic.lower() in c.lower()][:3]
        concepts = related or [c for c, _ in concept_counts.most_common(2)]
        rec = f"Review {topic}" + (f", focusing on {', '.join(concepts)}" if concepts else "") + \
              ", and practise explaining it aloud with a concrete example and its trade-offs."
        recs.append({
            "area": topic, "area_type": "topic", "recommendation": rec,
            "reason": f"Average score {avg} on '{topic}'" + (" — also weak in a previous interview (repeated weakness)." if repeated else "."),
            "evidence": {"average": avg, "repeated": repeated, "missing_concepts": concepts},
            "priority": round((100 - (avg or 0)) / 100 + (0.5 if repeated else 0), 3),
        })

    for criterion, score in sorted(criterion_scores.items(), key=lambda kv: kv[1] if kv[1] is not None else 100):
        if score is not None and score < LOW_CRITERION:
            recs.append({
                "area": criterion.replace("_", " ").title(), "area_type": "criterion" if criterion != "communication" else "communication",
                "recommendation": CRITERION_ADVICE[criterion],
                "reason": f"{criterion.replace('_', ' ').title()} averaged {score:.0f}/100 across answers.",
                "evidence": {"criterion": criterion, "score": score},
                "priority": round((100 - score) / 100, 3),
            })

    for gap in skill_gaps[:3]:
        if gap.get("gap", 0) >= 2 and gap["skill"] not in weak_topics:
            recs.append({
                "area": gap["skill"], "area_type": "resume",
                "recommendation": f"Prepare a concrete example demonstrating {gap['skill']} (a project, design decision or problem you solved), "
                                  f"since the role expects level {gap['required_level']}/5.",
                "reason": f"Estimated level {gap['candidate_level']}/5 vs required {gap['required_level']}/5.",
                "evidence": {"gap": gap["gap"], "priority": gap.get("priority")},
                "priority": round(float(gap.get("priority", 0)) / 5, 3),
            })

    recs.sort(key=lambda r: -r["priority"])
    seen, out = set(), []
    for r in recs:
        if r["area"] not in seen:
            seen.add(r["area"])
            out.append(r)
    return out[:limit]
