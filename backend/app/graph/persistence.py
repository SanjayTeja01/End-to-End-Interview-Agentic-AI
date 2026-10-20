"""Graph → PostgreSQL/MinIO persistence. Every important state change is written as it happens."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.domain.skills import score_to_level
from app.domain.text import normalize_key
from app.models import (
    CandidateSkill,
    Evaluation,
    InterviewCandidate,
    InterviewHistory,
    InterviewRecommendation,
    InterviewSession,
    Performance,
    Question,
    Readiness,
    Report,
)
from app.models.base import utcnow
from app.services.files import store_generated
from app.services.speech import get_tts
from storage.minio.keys import interview_media_key

log = logging.getLogger(__name__)

_QTYPE = {"technical": "technical", "resume": "resume", "behavioral": "behavioral"}


def persist_question(db: Session, state: dict, *, text: str, spoken_text: str, expected_points: list[str],
                     source: str, sources: list[dict]) -> dict:
    d = state["decision"]
    session = db.get(InterviewSession, uuid.UUID(state["session_id"]))
    seq = (db.execute(select(func.max(Question.sequence)).where(Question.session_id == session.id)).scalar() or 0) + 1
    qtype = "follow_up" if (d.get("kind") or "").startswith("follow_up") else _QTYPE.get(d.get("category"), "technical")
    q = Question(session_id=session.id, interview_id=session.interview_id, institute_id=session.institute_id,
                 sequence=seq, text=text, spoken_text=spoken_text, topic=d.get("topic"), skill=d.get("skill"),
                 difficulty=d["difficulty"], question_type=qtype, role=state["target_role"], source=source,
                 context_meta={"decision": d, "expected_points": expected_points, "rag_sources": sources,
                               "category": d.get("category")})
    db.add(q)
    db.flush()
    tts_file_id = _synthesize(db, session, spoken_text, q)
    q.tts_file_id = tts_file_id
    q.asked_at = utcnow()
    session.current_question_id = q.id
    session.question_index = seq
    session.current_topic = q.topic
    session.current_difficulty = q.difficulty
    session.progress = round(min(1.0, (seq - 1) / max(1, state["interview_config"]["question_count"])), 3)
    db.flush()
    log_event(log, "question_generated", session_id=str(session.id), sequence=seq, topic=q.topic, difficulty=q.difficulty,
              kind=d.get("kind"), source=source)
    return {"id": str(q.id), "sequence": seq, "text": text, "spoken_text": spoken_text, "topic": q.topic,
            "skill": q.skill, "difficulty": q.difficulty, "question_type": qtype, "category": d.get("category"),
            "expected_points": expected_points, "tts_file_id": str(tts_file_id) if tts_file_id else None}


def _synthesize(db: Session, session: InterviewSession, text: str, q: Question) -> uuid.UUID | None:
    from app.core.config import get_settings
    from app.services.speech import call_with_timeout

    try:
        wav = call_with_timeout(lambda: get_tts().synthesize(text), get_settings().tts_timeout_seconds, "speech synthesis")
    except Exception:  # noqa: BLE001 — TTS failure must not stop the interview; client falls back
        log.exception("tts_failed", extra={"data": {"question_id": str(q.id)}})
        return None
    if not wav:
        return None
    key = interview_media_key(session.institute_id, session.interview_id, session.candidate_id, "tts", "wav")
    f = store_generated(db, wav, key=key, mime="audio/wav", owner_id=session.candidate_id,
                        institute_id=session.institute_id, file_type="tts", filename=f"question-{q.sequence}.wav")
    return f.id


def persist_evaluation(db: Session, state: dict, *, answer_id: str, question: dict, ev: dict) -> str:
    existing = db.execute(select(Evaluation).where(Evaluation.answer_id == uuid.UUID(answer_id))).scalar_one_or_none()
    if existing:  # idempotent on task retry
        return str(existing.id)
    row = Evaluation(
        answer_id=uuid.UUID(answer_id), question_id=uuid.UUID(question["id"]), session_id=uuid.UUID(state["session_id"]),
        candidate_id=uuid.UUID(state["candidate_id"]), institute_id=uuid.UUID(state["institution_id"]),
        topic=question.get("topic"), skill=question.get("skill"), difficulty=question["difficulty"],
        **{k: ev[k] for k in ("technical_correctness", "relevance", "completeness", "clarity", "depth", "communication",
                              "overall_score", "confidence", "band", "strengths", "weaknesses", "missing_concepts",
                              "improvement_actions", "suggested_answer_structure", "practice_topics", "evidence",
                              "rubric_weights", "rubric_version")},
    )
    db.add(row)
    db.flush()
    log_event(log, "evaluation_completed", session_id=state["session_id"], question_id=question["id"],
              score=ev["overall_score"], band=ev["band"])
    return str(row.id)


def set_next_question_reason(db: Session, evaluation_id: str | None, reason: str) -> None:
    if evaluation_id:
        row = db.get(Evaluation, uuid.UUID(evaluation_id))
        if row and not row.next_question_reason:
            row.next_question_reason = reason


def persist_outcomes(db: Session, state: dict, *, performance: dict, readiness: dict, recommendations: list[dict],
                     report_content: dict) -> str:
    sid, cid, iid, inst = (uuid.UUID(state[k]) for k in ("session_id", "candidate_id", "interview_id", "institution_id"))
    session = db.get(InterviewSession, sid)
    if not db.execute(select(Performance).where(Performance.session_id == sid)).scalar_one_or_none():
        db.add(Performance(session_id=sid, interview_id=iid, candidate_id=cid, institute_id=inst,
                           role_name=state["target_role"], overall_score=performance["overall_score"],
                           criterion_scores=performance["criterion_scores"], topic_performance=performance["topic_performance"],
                           skill_performance=performance["skill_performance"],
                           difficulty_progression=performance["difficulty_progression"],
                           method_version=performance["method_version"]))
    if not db.execute(select(Readiness).where(Readiness.session_id == sid)).scalar_one_or_none():
        db.add(Readiness(session_id=sid, candidate_id=cid, institute_id=inst, role_id=uuid.UUID(state["role_id"]),
                         role_name=state["target_role"], components=readiness["components"], overall=readiness["overall"],
                         level=readiness["level"], evidence=readiness["evidence"], weights=readiness["weights"],
                         method_version=readiness["method_version"]))
    for r in recommendations:
        db.add(InterviewRecommendation(candidate_id=cid, institute_id=inst, session_id=sid, **r))
    version = (db.execute(select(func.max(Report.version)).where(Report.session_id == sid)).scalar() or 0) + 1
    report = Report(session_id=sid, interview_id=iid, candidate_id=cid, institute_id=inst, version=version,
                    content=report_content, meta={"generated_by": "report_agent"})
    db.add(report)
    if not db.execute(select(InterviewHistory).where(InterviewHistory.session_id == sid)).scalar_one_or_none():
        db.add(InterviewHistory(
            session_id=sid, interview_id=iid, candidate_id=cid, institute_id=inst, role_name=state["target_role"],
            overall_score=performance["overall_score"], weak_topics=state.get("weak_topics", []),
            strong_topics=state.get("strong_topics", []),
            difficulty_responses=[{"difficulty": p["difficulty"], "score": p["score"]} for p in performance["difficulty_progression"]],
            question_summaries=[{"sequence": q["sequence"], "topic": q.get("topic"), "score": q.get("score")}
                                for q in report_content.get("questions", [])],
            repeated_mistakes=[r["area"] for r in recommendations if (r.get("evidence") or {}).get("repeated")],
        ))
    _update_candidate_skills(db, cid, inst, performance, sid)
    session.status = "completed"
    session.ended_at = utcnow()
    session.progress = 1.0
    session.termination_reason = state.get("stop_reason")
    ic = db.execute(select(InterviewCandidate).where(InterviewCandidate.interview_id == iid,
                                                     InterviewCandidate.candidate_id == cid)).scalar_one_or_none()
    if ic:
        ic.participation_status = "completed"
    db.flush()
    log_event(log, "interview_completed", session_id=str(sid), score=performance["overall_score"],
              readiness=readiness["overall"], stop_reason=state.get("stop_reason"))
    return str(report.id)


def _update_candidate_skills(db: Session, cid: uuid.UUID, inst: uuid.UUID, performance: dict, sid: uuid.UUID) -> None:
    for skill, perf in (performance.get("skill_performance") or {}).items():
        if perf.get("average") is None:
            continue
        key = normalize_key(skill)
        level = score_to_level(perf["average"])
        row = db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == cid, CandidateSkill.skill_key == key,
                                                      CandidateSkill.source == "interview")).scalar_one_or_none()
        ev = {"session_id": str(sid), "average": perf["average"], "count": perf["count"]}
        conf = min(0.95, 0.4 + 0.15 * perf["count"])
        if row:
            row.proficiency = int(round(0.6 * level + 0.4 * row.proficiency))
            row.evidence = ([ev] + list(row.evidence or []))[:5]
            row.confidence = max(row.confidence, conf)
        else:
            db.add(CandidateSkill(candidate_id=cid, institute_id=inst, skill=skill, skill_key=key,
                                  proficiency=int(round(level)), source="interview", evidence=[ev], confidence=conf))
