from datetime import datetime, timedelta, timezone

import pytest

from app.domain import eligibility, lifecycle

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def test_valid_and_invalid_transitions():
    lifecycle.assert_transition("draft", "pending_approval")
    lifecycle.assert_transition("approved", "active")
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.assert_transition("draft", "active")
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.assert_transition("cancelled", "active")


def test_cannot_activate_without_skill_approval():
    ok, msg = lifecycle.can_activate(status="approved", skill_approval_state="pending", has_approved_skills=True)
    assert not ok and "approved" in msg
    ok, _ = lifecycle.can_activate(status="pending_approval", skill_approval_state="approved", has_approved_skills=True)
    assert not ok
    ok, _ = lifecycle.can_activate(status="approved", skill_approval_state="approved", has_approved_skills=True)
    assert ok


def test_scheduled_becomes_active_and_completes():
    start, end = NOW - timedelta(minutes=1), NOW + timedelta(hours=1)
    assert lifecycle.effective_status("scheduled", start, end, NOW) == "active"
    assert lifecycle.effective_status("active", start, NOW - timedelta(seconds=1), NOW) == "completed"
    assert lifecycle.activation_target(NOW + timedelta(hours=1), NOW) == "scheduled"


def _elig(**kw):
    base = dict(candidate_institute_id="i1", interview_institute_id="i1", candidate_active=True, interview_status="active",
                start=None, end=None, interview_role="AI/ML Engineer", candidate_roles=["AI/ML Engineer"],
                eligibility_config={}, assignment_status=None, now=NOW)
    base.update(kw)
    return eligibility.evaluate(**base)


def test_role_match_eligible():
    r = _elig()
    assert r.eligible and r.joinable and r.match_score == 1.0


def test_role_mismatch_not_eligible():
    r = _elig(candidate_roles=["DevOps Engineer"])
    assert not r.eligible and not r.visible


def test_other_institution_never_eligible_even_if_assigned():
    r = _elig(interview_institute_id="i2", assignment_status="assigned")
    assert not r.eligible


def test_draft_interview_not_visible():
    assert not _elig(interview_status="draft").visible


def test_revoked_blocks_access():
    assert not _elig(assignment_status="revoked").eligible


def test_assigned_only_mode():
    assert not _elig(eligibility_config={"mode": "assigned_only"}).eligible
    assert _elig(eligibility_config={"mode": "assigned_only"}, assignment_status="assigned").eligible


def test_scheduled_visible_not_joinable():
    r = _elig(interview_status="scheduled", start=NOW + timedelta(hours=2))
    assert r.visible and not r.joinable


def test_semantic_similarity_can_add_match():
    r = _elig(candidate_roles=["Machine Learning Engineer"], semantic_scores={"Machine Learning Engineer": 0.9})
    assert r.eligible


def test_weak_semantic_similarity_does_not_match():
    # Generic overlap like "Engineer" must not make a DevOps candidate eligible for an AI/ML interview
    r = _elig(candidate_roles=["DevOps Engineer"], semantic_scores={"DevOps Engineer": 0.6})
    assert not r.eligible
