import pytest

from app.domain import performance, readiness


def _ev(cat, score, diff="medium", seq=1, topic="t", **crit):
    base = {c: score / 10 for c in ("technical_correctness", "relevance", "completeness", "clarity", "depth", "communication")}
    base.update(crit)
    return {"category": cat, "overall_score": score, "difficulty": diff, "sequence": seq, "topic": topic, "skill": "s", **base}


def test_readiness_weights_default():
    assert readiness.DEFAULT_WEIGHTS == {"technical": 0.35, "problem_solving": 0.20, "communication": 0.20,
                                         "behavioral": 0.15, "resume": 0.10}


def test_readiness_missing_components_renormalised():
    r = readiness.compute([_ev("technical", 80)], resume_skill_coverage=None)
    assert r["components"]["behavioral"] is None
    assert "behavioral" in r["evidence"]["excluded_components"]
    assert abs(sum(r["effective_weights"].values()) - 1.0) < 1e-3
    assert 70 <= r["overall"] <= 85


def test_readiness_has_disclaimer_and_no_guarantee():
    r = readiness.compute([_ev("technical", 95)], resume_skill_coverage=1.0)
    assert "not a prediction or guarantee" in r["disclaimer"]
    assert r["level"] == "interview_ready"


def test_readiness_levels():
    assert readiness.level_for(40) == "needs_preparation"
    assert readiness.level_for(55) == "developing"
    assert readiness.level_for(70) == "nearly_ready"


def test_readiness_invalid_weights():
    with pytest.raises(ValueError):
        readiness.compute([], resume_skill_coverage=None, weights={"technical": 1.0})


def test_performance_aggregation():
    evs = [_ev("technical", 80, "medium", 1, "A"), _ev("technical", 40, "hard", 2, "A"), _ev("technical", 60, "easy", 3, "B")]
    p = performance.aggregate(evs)
    assert p["overall_score"] == 60
    assert p["topic_performance"]["A"] == {"average": 60, "count": 2}
    assert [d["difficulty"] for d in p["difficulty_progression"]] == ["medium", "hard", "easy"]
    assert p["criterion_scores"]["technical_correctness"] == 60


def test_trend():
    t = performance.trend([("i1", 50), ("i2", 70)])
    assert t["direction"] == "up" and t["delta"] == 20
