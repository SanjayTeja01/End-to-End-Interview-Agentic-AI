"""Deterministic candidate eligibility. Semantic similarity can only *add* a match signal;
backend rules (tenant, status, schedule, revocation) are always authoritative."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.lifecycle import ACTIVE, SCHEDULED, effective_status
from app.domain.text import jaccard, normalize_key

DEFAULT_MIN_SIMILARITY = 0.5  # lexical (token overlap) threshold
DEFAULT_MIN_SEMANTIC = 0.85   # embedding cosine threshold — strict, because role names share generic words


@dataclass
class EligibilityResult:
    eligible: bool
    visible: bool  # may be listed (e.g. scheduled but not yet joinable)
    joinable: bool
    reason: str
    match_score: float


def role_match_score(interview_role: str, candidate_roles: list[str]) -> float:
    """Lexical match: 1.0 for the same normalised role, otherwise best token-overlap (Jaccard)."""
    target = normalize_key(interview_role)
    best = 0.0
    for r in candidate_roles:
        if normalize_key(r) == target:
            return 1.0
        best = max(best, jaccard(r, interview_role))
    return round(best, 3)


def semantic_match_score(candidate_roles: list[str], semantic_scores: dict[str, float] | None) -> float:
    if not semantic_scores:
        return 0.0
    return round(max((float(semantic_scores.get(r, 0.0)) for r in candidate_roles), default=0.0), 3)


def evaluate(*, candidate_institute_id, interview_institute_id, candidate_active: bool, interview_status: str,
             start: datetime | None, end: datetime | None, interview_role: str, candidate_roles: list[str],
             eligibility_config: dict, assignment_status: str | None, semantic_scores: dict[str, float] | None = None,
             now: datetime | None = None) -> EligibilityResult:
    if candidate_institute_id != interview_institute_id:
        return EligibilityResult(False, False, False, "Interview belongs to a different institution", 0.0)
    if not candidate_active:
        return EligibilityResult(False, False, False, "Candidate account is not active", 0.0)
    if assignment_status in ("revoked", "ineligible"):
        return EligibilityResult(False, False, False, f"Candidate access {assignment_status} by institution", 0.0)

    status = effective_status(interview_status, start, end, now)
    if status not in (ACTIVE, SCHEDULED):
        return EligibilityResult(False, False, False, f"Interview is not open (status: {status})", 0.0)

    mode = eligibility_config.get("mode", "role_match")  # role_match | assigned_only | all_students
    min_sim = float(eligibility_config.get("min_similarity", DEFAULT_MIN_SIMILARITY))
    min_sem = float(eligibility_config.get("min_semantic_similarity", DEFAULT_MIN_SEMANTIC))
    lexical = role_match_score(interview_role, candidate_roles)
    semantic = semantic_match_score(candidate_roles, semantic_scores)
    score = max(lexical, semantic)

    if assignment_status == "assigned":
        reason, ok = "Assigned by institution", True
    elif mode == "assigned_only":
        reason, ok = "Interview is restricted to assigned candidates", False
    elif mode == "all_students":
        reason, ok = "Open to all students of the institution", True
    else:
        ok = lexical >= min_sim or semantic >= min_sem
        reason = (f"Target role matches '{interview_role}' (score {score:.2f})" if ok
                  else f"No target role matches '{interview_role}' (best score {score:.2f})")

    joinable = ok and status == ACTIVE
    return EligibilityResult(ok, ok, joinable, reason if status == ACTIVE or not ok else f"{reason}; opens at start time", score)
