"""LangGraph orchestration of the specialised agents (Supervisor-routed).

One compiled graph handles three entry actions chosen by the Supervisor:
  initialize      → load context → plan → decide → (RAG?) → generate first question → END (await answer)
  process_answer  → evaluate → update profile → decide → (RAG?) → next question | finalize
                    (the runtime runs this in two committed stages: evaluate_only=True stops after the evaluation
                    and profile update; next_question then decides and asks using that stored evaluation)
  next_question   → decide → (RAG?) → next question | finalize
  finalize        → performance → readiness → recommendations → report → END
The graph stops at every point where it must wait for the candidate; state is persisted to PostgreSQL
between turns, so no long-lived process is required and sessions survive restarts.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.adaptive_interview import AdaptiveInterviewAgent
from app.agents.answer_evaluation import AnswerEvaluationAgent
from app.agents.performance import PerformanceAgent
from app.agents.planning import InterviewPlanningAgent
from app.agents.rag_knowledge import RAGKnowledgeAgent
from app.agents.readiness import ReadinessAgent
from app.agents.report import ReportAgent
from app.domain import adaptive, recommendations
from app.graph import persistence
from app.graph.context import load_context
from app.graph.state import InterviewState
from app.services import realtime
from app.services.llm import LLMError

log = logging.getLogger(__name__)


def _db(config: RunnableConfig) -> Session:
    return config["configurable"]["db"]


def RunnableConfigFor(db: Session) -> RunnableConfig:  # noqa: N802 — used to call a node directly
    return {"configurable": {"db": db}}


def _elapsed(state: InterviewState) -> float:
    started = state.get("started_at")
    if not started:
        return 0.0
    return (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()


# ----------------------------------------------------------------- Supervisor
def supervisor(state: InterviewState) -> dict:
    """Validates the requested action against state; recovery picks a safe action when inconsistent."""
    action = state.get("next_action", "initialize")
    if action == "process_answer" and not state.get("candidate_answer"):
        action = "finalize" if (state.get("candidate_ended") or state.get("terminated")) else "await_answer"
    if action == "initialize" and state.get("plan"):
        action = "await_answer"  # already initialised (duplicate start request)
    if action == "next_question" and not state.get("evaluation"):
        action = "await_answer"  # never pick an adaptive question without the evaluation it depends on
    return {"next_action": action}


def route_supervisor(state: InterviewState) -> str:
    return {"initialize": "load_context", "process_answer": "evaluate_answer", "next_question": "decide_next",
            "finalize": "performance"}.get(state["next_action"], END)


def _mark(state: InterviewState, step: str) -> dict:
    """Turn timeline: wall-clock time of each step, copied onto the answer by the runtime."""
    return {**(state.get("turn_marks") or {}), step: time.time()}


# ----------------------------------------------------------------- Initialisation
def load_context_node(state: InterviewState, config: RunnableConfig) -> dict:
    ctx = load_context(_db(config), uuid.UUID(state["session_id"]))
    return {**ctx, "topic_stats": {}, "asked_questions": [], "evaluations": [], "transcript": [],
            "question_difficulty": ctx["interview_config"]["initial_difficulty"], "current_topic": None,
            "interview_progress": {"asked": 0, "answered": 0}, "errors": []}


def plan_node(state: InterviewState) -> dict:
    return InterviewPlanningAgent().plan(state)


# ----------------------------------------------------------------- Turn processing
def evaluate_node(state: InterviewState, config: RunnableConfig) -> dict:
    db = _db(config)
    ans = state["candidate_answer"]
    q = state["current_question"]
    # LLM failures propagate: the worker retries a bounded number of times and otherwise marks the answer
    # evaluation_failed. A score is never invented, and the next question is never chosen without this evaluation.
    ev = AnswerEvaluationAgent().evaluate(question=q, transcript=ans["transcript"],
                                          weights=state["interview_config"]["rubric_weights"],
                                          role=state["target_role"], knowledge_context=state.get("retrieved_context", ""))
    marks = _mark(state, "evaluation_completed")
    eval_id = persistence.persist_evaluation(db, state, answer_id=ans["answer_id"], question=q, ev=ev)
    compact = compact_evaluation(eval_id, q, ev)
    stats = {k: adaptive.TopicStat.from_dict(v) for k, v in state.get("topic_stats", {}).items()}
    topic = q.get("topic") or "general"
    stats[topic] = adaptive.update_topic_stat(stats.get(topic, adaptive.TopicStat()), ev["overall_score"], ev["band"])
    weak, strong = adaptive.split_topics(stats)
    evaluations = [*state.get("evaluations", []), compact]
    live = PerformanceAgent().session_performance(evaluations)
    realtime.publish(state["session_id"], "evaluation_update", {
        "question_id": q["id"], "score": ev["overall_score"], "band": ev["band"], "topic": topic,
        "running_score": live["overall_score"], "answered": len(evaluations)})
    progress = {**state["interview_progress"], "answered": len(evaluations)}
    marks = {**marks, "profile_updated": time.time()}
    return {
        "turn_marks": marks, "next_action": "next_question",
        "evaluation": {**compact, "summary": ev["evidence"].get("summary")},
        "evaluations": evaluations,
        "topic_stats": {k: v.__dict__ for k, v in stats.items()},
        "weak_topics": weak, "strong_topics": strong, "performance": live,
        "last_turn": {"question": q["text"], "answer": ans["transcript"], "summary": ev["evidence"].get("summary"),
                      "band": ev["band"]},
        "transcript": [*state.get("transcript", []), {"sequence": q["sequence"], "question": q["text"],
                                                      "answer": ans["transcript"]}],
        "candidate_answer": None, "interview_progress": progress,
    }


def compact_evaluation(eval_id: str, q: dict, ev: dict) -> dict:
    """The per-answer evidence kept in the session's performance profile (no transcript, no free text)."""
    return {"evaluation_id": eval_id, "question_id": q["id"], "sequence": q["sequence"], "topic": q.get("topic"),
            "skill": q.get("skill"), "category": q.get("category"), "difficulty": q["difficulty"],
            **{k: ev[k] for k in ("technical_correctness", "relevance", "completeness", "clarity", "depth",
                                  "communication", "overall_score", "band", "confidence", "missing_concepts")}}


def route_after_evaluate(state: InterviewState) -> str:
    return END if state.get("evaluate_only") else "decide_next"


def decide_node(state: InterviewState, config: RunnableConfig) -> dict:
    cfg = state["interview_config"]
    last = state.get("evaluation")
    decision = adaptive.decide_next(
        plan=[adaptive.PlanItem.from_dict(p) for p in state["plan"]],
        stats={k: adaptive.TopicStat.from_dict(v) for k, v in state.get("topic_stats", {}).items()},
        current_topic=state.get("current_topic"), current_difficulty=state.get("question_difficulty") or cfg["initial_difficulty"],
        last_band=last["band"] if last else None, asked=state["interview_progress"]["asked"],
        question_count=cfg["question_count"], elapsed_seconds=_elapsed(state),
        duration_seconds=cfg["duration_minutes"] * 60, adaptive=cfg["adaptive_mode"],
        candidate_ended=bool(state.get("candidate_ended")), terminated=bool(state.get("terminated")),
        evidence=adaptive.TurnEvidence.from_evaluation(last), config=adaptive.AdaptiveConfig.from_settings(),
    ).to_dict()
    if last:
        persistence.set_next_question_reason(_db(config), last.get("evaluation_id"), decision["reason"])
    log.info("adaptive_decision", extra={"data": {
        "session_id": state["session_id"], "after_sequence": last.get("sequence") if last else 0,
        "last_score": last.get("overall_score") if last else None, "signal": decision.get("signal"),
        "action": decision["action"], "kind": decision.get("kind"), "topic": decision.get("topic"),
        "difficulty": decision.get("difficulty"), "focus": decision.get("focus"), "reason": decision["reason"]}})
    out: dict = {"decision": decision, "turn_marks": _mark(state, "next_question_decided")}
    if decision["action"] == "complete":
        out["stop_reason"] = decision["stop_reason"]
    return out


def route_after_decide(state: InterviewState) -> str:
    if state["decision"]["action"] == "complete":
        return "performance"
    return "retrieve_context" if RAGKnowledgeAgent.needs_retrieval(state) else "generate_question"


def retrieve_node(state: InterviewState) -> dict:
    try:
        return RAGKnowledgeAgent().retrieve_for_topic(state)
    except Exception:  # noqa: BLE001 — RAG is supporting context; continue without it
        log.exception("rag_retrieval_failed", extra={"data": {"session_id": state["session_id"]}})
        return {"retrieved_context": "", "retrieved_sources": []}


def generate_question_node(state: InterviewState, config: RunnableConfig) -> dict:
    db = _db(config)
    d = state["decision"]
    agent = AdaptiveInterviewAgent()
    errors = list(state.get("errors", []))
    try:
        gen = agent.generate(state)
        text, transition, points, source = gen.question, gen.spoken_transition, gen.expected_points, \
            ("rag" if state.get("retrieved_sources") else "generated")
    except LLMError:
        # Recovery: a templated question that still follows the adaptive decision (topic, difficulty, kind and the
        # concepts to target, all taken from the real evaluation) keeps the interview moving.
        text = _fallback_question(d)
        transition, points, source = "", list(d.get("focus") or []), "fallback"
        errors.append("question_generation_fallback")
    first = state["interview_progress"]["asked"] == 0
    intro = agent.greeting(state.get("candidate_name", ""), state["interview_config"]["name"],
                           state["interview_config"]["question_count"], state["interview_config"]["duration_minutes"]) if first else transition
    spoken = f"{intro} {text}".strip()
    q = persistence.persist_question(db, state, text=text, spoken_text=spoken, expected_points=points, source=source,
                                     sources=state.get("retrieved_sources", []))
    progress = {**state["interview_progress"], "asked": q["sequence"]}
    # Published by the runtime only after this question is committed, so a client that re-reads state on the
    # event always sees it.
    event = {"question": {k: q[k] for k in ("id", "sequence", "text", "spoken_text", "topic", "difficulty", "question_type")},
             "has_audio": bool(q["tts_file_id"]), "progress": progress,
             "question_count": state["interview_config"]["question_count"], "reason": d["reason"]}
    return {"current_question": q, "current_topic": q["topic"], "question_difficulty": q["difficulty"],
            "asked_questions": [*state.get("asked_questions", []), {"id": q["id"], "text": text, "topic": q["topic"]}],
            "interview_progress": progress, "next_action": "await_answer", "errors": errors, "question_event": event,
            "turn_marks": _mark(state, "next_question_generated")}


def _fallback_question(d: dict) -> str:
    topic = (d.get("topic") or "your recent work").removeprefix("Project: ")
    focus = (d.get("focus") or [None])[0]
    if focus and d.get("kind") in ("follow_up_gap", "follow_up_probe"):
        return f"You didn't mention {focus}. How does it fit into {topic}?"
    if d.get("kind") == "follow_up_clarify":
        return f"Could you make that more concrete? Walk me through one specific example of {topic}."
    return {
        "easy": f"Could you explain the key ideas behind {topic} in your own words?",
        "medium": f"Describe a realistic situation where you would apply {topic}. How would you approach it?",
        "hard": f"What are the main trade-offs and failure modes you would consider when designing with {topic}?",
    }.get(d.get("difficulty"), f"Tell me about your experience with {topic}.")


# ----------------------------------------------------------------- Finalisation
def performance_node(state: InterviewState) -> dict:
    realtime.publish(state["session_id"], "interview_finalizing", {"stop_reason": state.get("stop_reason")})
    return {"performance": PerformanceAgent().session_performance(state.get("evaluations", []))}


def readiness_node(state: InterviewState) -> dict:
    return {"readiness": ReadinessAgent().assess(
        state.get("evaluations", []), required_skills=state.get("required_skills", []),
        resume_skill_keys=set(state.get("resume_skill_keys", [])), weights=state["interview_config"]["readiness_weights"])}


def recommendations_node(state: InterviewState) -> dict:
    missing = [c for e in state.get("evaluations", []) for c in e.get("missing_concepts", [])]
    recs = recommendations.generate(
        topic_performance=state["performance"].get("topic_performance", {}),
        criterion_scores=state["performance"].get("criterion_scores", {}), missing_concepts=missing,
        weak_topics=state.get("weak_topics", []), historical_weak_topics=state.get("historical_weak_topics", []),
        skill_gaps=state.get("skill_gaps", []))
    return {"recommendations": recs}


def report_node(state: InterviewState, config: RunnableConfig) -> dict:
    db = _db(config)
    from app.services.reports import session_questions

    questions = session_questions(db, uuid.UUID(state["session_id"]))
    content = ReportAgent().build(state=state, questions=questions, performance=state["performance"],
                                  readiness=state["readiness"], recommendations=state["recommendations"])
    report_id = persistence.persist_outcomes(db, state, performance=state["performance"], readiness=state["readiness"],
                                             recommendations=state["recommendations"], report_content=content)
    realtime.publish(state["session_id"], "interview_completed", {
        "report_id": report_id, "overall_score": state["performance"]["overall_score"],
        "closing": AdaptiveInterviewAgent.closing(), "stop_reason": state.get("stop_reason")})
    return {"report_id": report_id, "next_action": "done"}


@lru_cache
def build_graph():  # noqa: ANN201
    g = StateGraph(InterviewState)
    g.add_node("supervisor", supervisor)
    g.add_node("load_context", load_context_node)
    g.add_node("plan_interview", plan_node)
    g.add_node("evaluate_answer", evaluate_node)
    g.add_node("decide_next", decide_node)
    g.add_node("retrieve_context", retrieve_node)
    g.add_node("generate_question", generate_question_node)
    g.add_node("performance", performance_node)
    g.add_node("readiness", readiness_node)
    g.add_node("recommendations", recommendations_node)
    g.add_node("report", report_node)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route_supervisor,
                            {"load_context": "load_context", "evaluate_answer": "evaluate_answer",
                             "decide_next": "decide_next", "performance": "performance", END: END})
    g.add_edge("load_context", "plan_interview")
    g.add_edge("plan_interview", "decide_next")
    g.add_conditional_edges("evaluate_answer", route_after_evaluate, {END: END, "decide_next": "decide_next"})
    g.add_conditional_edges("decide_next", route_after_decide,
                            {"performance": "performance", "retrieve_context": "retrieve_context",
                             "generate_question": "generate_question"})
    g.add_edge("retrieve_context", "generate_question")
    g.add_edge("generate_question", END)
    g.add_edge("performance", "readiness")
    g.add_edge("readiness", "recommendations")
    g.add_edge("recommendations", "report")
    g.add_edge("report", END)
    return g.compile()


def run(db: Session, state: dict) -> dict:
    """Execute one graph pass and return the new state (caller persists it)."""
    return build_graph().invoke(state, config={"configurable": {"db": db}, "recursion_limit": 40})
