import pytest

from app.domain import rubric, skills


def test_default_weights_sum_to_one():
    assert abs(sum(rubric.DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9
    assert rubric.DEFAULT_WEIGHTS["technical_correctness"] == 0.30


def test_final_score_formula():
    scores = {"technical_correctness": 8, "relevance": 9, "completeness": 7, "clarity": 6, "depth": 5, "communication": 10}
    expected = (0.30 * 8 + 0.20 * 9 + 0.20 * 7 + 0.15 * 6 + 0.10 * 5 + 0.05 * 10) * 10
    result = rubric.compute_final_score(scores, rubric.DEFAULT_WEIGHTS)
    assert result.overall == pytest.approx(expected)
    assert result.overall == 75.0 and result.band == "strong"  # 75 is the strong threshold


def test_bands():
    assert rubric.band_for(80) == "strong"
    assert rubric.band_for(60) == "average"
    assert rubric.band_for(30) == "weak"


def test_out_of_range_criterion_rejected():
    with pytest.raises(ValueError):
        rubric.compute_final_score({c: 11 for c in rubric.CRITERIA}, rubric.DEFAULT_WEIGHTS)


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        rubric.validate_weights({**rubric.DEFAULT_WEIGHTS, "depth": 0.5})


def test_behavioral_uses_behavioral_weights():
    assert rubric.weights_for("behavioral") == rubric.BEHAVIORAL_WEIGHTS


def test_gap_and_priority():
    assert skills.skill_gap(4, 2) == 2
    assert skills.skill_gap(3, 4.5) == 0  # exceeding requirement is not a gap
    assert skills.skill_priority(2, 0.8) == pytest.approx(1.6)


def test_resume_evidence_weighs_less_than_interview():
    resume_only = skills.estimate_candidate_level([skills.SkillEvidence("resume", 5, 0.9)])
    mixed = skills.estimate_candidate_level([skills.SkillEvidence("resume", 5, 0.9), skills.SkillEvidence("interview", 1, 0.9)])
    assert resume_only == 5
    assert mixed < 3  # interview evidence dominates resume claims


def test_compute_gaps_sorted_by_priority():
    reqs = [
        {"skill": "Python", "skill_key": "python", "required_level": 4, "importance_weight": 1.0},
        {"skill": "Docker", "skill_key": "docker", "required_level": 3, "importance_weight": 0.3},
    ]
    gaps = skills.compute_gaps(reqs, {"python": [skills.SkillEvidence("resume", 2, 1.0)]})
    assert [g.skill for g in gaps] == ["Python", "Docker"]
    assert gaps[0].gap == 2 and gaps[1].gap == 3
    assert gaps[0].priority == 2.0 and gaps[1].priority == pytest.approx(0.9)


def test_no_evidence_means_missing():
    assert skills.estimate_candidate_level([]) == 0
