"""Supervisor routing (no LangGraph runtime needed)."""
from app.graph import workflow


def test_supervisor_routes_actions():
    assert workflow.route_supervisor(workflow.supervisor({"next_action": "initialize"}) | {}) == "load_context"
    st = {"next_action": "process_answer", "candidate_answer": {"answer_id": "a"}}
    assert workflow.route_supervisor({**st, **workflow.supervisor(st)}) == "evaluate_answer"
    st = {"next_action": "finalize"}
    assert workflow.route_supervisor({**st, **workflow.supervisor(st)}) == "performance"


def test_supervisor_recovers_from_inconsistent_requests():
    st = {"next_action": "process_answer", "candidate_answer": None}
    assert workflow.supervisor(st)["next_action"] == "await_answer"
    st = {"next_action": "process_answer", "candidate_answer": None, "candidate_ended": True}
    assert workflow.supervisor(st)["next_action"] == "finalize"
    st = {"next_action": "initialize", "plan": [{"topic": "x"}]}
    assert workflow.supervisor(st)["next_action"] == "await_answer"


def test_fallback_question_by_difficulty():
    assert "trade-offs" in workflow._fallback_question({"topic": "Caching", "difficulty": "hard"})
    assert "Project" not in workflow._fallback_question({"topic": "Project: Foo", "difficulty": "easy"})
