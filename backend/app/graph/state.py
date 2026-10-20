"""Shared LangGraph state. JSON-serialisable only — binaries are referenced by object/file ids."""
from __future__ import annotations

from typing import Any, TypedDict


class InterviewState(TypedDict, total=False):
    # identity / tenancy
    session_id: str
    interview_id: str
    user_id: str
    institution_id: str
    candidate_id: str
    candidate_name: str
    target_role: str
    role_id: str

    # candidate & knowledge memory
    candidate_profile: dict[str, Any]
    resume_data: dict[str, Any]
    resume_skill_keys: list[str]
    role_requirements: dict[str, Any]
    required_skills: list[dict[str, Any]]
    skill_gaps: list[dict[str, Any]]
    interview_config: dict[str, Any]
    knowledge_available: bool
    has_behavioral_guidelines: bool

    # historical memory
    interview_history: list[dict[str, Any]]
    historical_weak_topics: list[str]
    historical_strong_topics: list[str]

    # planning / adaptive policy
    plan: list[dict[str, Any]]
    plan_rationale: str
    topic_stats: dict[str, dict[str, Any]]
    decision: dict[str, Any]
    current_topic: str | None
    question_difficulty: str
    current_question: dict[str, Any] | None
    asked_questions: list[dict[str, Any]]
    last_turn: dict[str, Any]

    # session memory
    candidate_answer: dict[str, Any] | None
    transcript: list[dict[str, Any]]
    evaluation: dict[str, Any] | None
    evaluations: list[dict[str, Any]]
    weak_topics: list[str]
    strong_topics: list[str]
    retrieved_context: str
    retrieved_sources: list[dict[str, Any]]
    interview_progress: dict[str, Any]
    started_at: str
    candidate_ended: bool
    terminated: bool
    stop_reason: str | None

    # outcomes
    performance: dict[str, Any]
    readiness: dict[str, Any]
    recommendations: list[dict[str, Any]]
    report_id: str | None

    # control
    next_action: str  # initialize | process_answer | next_question | finalize | await_answer | done
    errors: list[str]
    evaluate_only: bool  # process_answer stops after evaluation + profile update (runtime commits, then asks next)
    turn_marks: dict[str, float]  # step -> wall-clock time for the current turn (moved onto the answer)
    question_event: dict[str, Any] | None  # realtime "question" payload, published after the commit
