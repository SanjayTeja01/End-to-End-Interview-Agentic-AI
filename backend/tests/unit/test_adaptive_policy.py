from app.domain.adaptive import Decision, PlanItem, TopicStat, decide_next, shift_difficulty, split_topics, update_topic_stat


def _plan():
    return [
        PlanItem("Neural networks", "Deep Learning", "technical", 1.5, "role", max_questions=2),
        PlanItem("SQL indexing", "Databases", "technical", 1.0, "role", max_questions=2),
        PlanItem("Project: Recommender", "Python", "resume", 0.75, "resume", max_questions=2),
    ]


def _decide(**kw):
    base = dict(plan=_plan(), stats={}, current_topic=None, current_difficulty="medium", last_band=None, asked=0,
                question_count=8, elapsed_seconds=0, duration_seconds=1800, adaptive=True)
    base.update(kw)
    return decide_next(**base)


def test_difficulty_shifts():
    assert shift_difficulty("medium", "strong") == "hard"
    assert shift_difficulty("medium", "average") == "medium"
    assert shift_difficulty("medium", "weak") == "easy"
    assert shift_difficulty("hard", "strong") == "hard"
    assert shift_difficulty("easy", "weak") == "easy"


def test_first_question_picks_highest_priority():
    d = _decide()
    assert d.action == "ask" and d.topic == "Neural networks" and d.kind == "new_topic"


def test_strong_answer_goes_deeper_and_harder():
    stats = {"Neural networks": update_topic_stat(TopicStat(), 85, "strong")}
    d = _decide(stats=stats, current_topic="Neural networks", last_band="strong", asked=1)
    assert d.difficulty == "hard" and d.kind == "follow_up_deeper" and d.topic == "Neural networks"


def test_average_answer_keeps_difficulty_and_probes():
    stats = {"Neural networks": update_topic_stat(TopicStat(), 62, "average")}
    d = _decide(stats=stats, current_topic="Neural networks", last_band="average", asked=1)
    assert d.difficulty == "medium" and d.kind == "follow_up_probe"


def test_weak_answer_simplifies():
    stats = {"Neural networks": update_topic_stat(TopicStat(), 30, "weak")}
    d = _decide(stats=stats, current_topic="Neural networks", last_band="weak", asked=1)
    assert d.difficulty == "easy" and d.kind == "follow_up_foundational"


def test_repeated_weakness_marks_topic_and_moves_on():
    s = TopicStat()
    update_topic_stat(s, 30, "weak")
    update_topic_stat(s, 25, "weak")
    assert s.status == "weak"
    d = _decide(stats={"Neural networks": s}, current_topic="Neural networks", last_band="weak", asked=2,
                current_difficulty="easy")
    assert d.topic == "SQL indexing" and d.kind == "new_topic"
    assert "marked weak" in d.reason
    weak, strong = split_topics({"Neural networks": s})
    assert weak == ["Neural networks"] and strong == []


def test_repeated_strength_reduces_repetition():
    s = TopicStat()
    update_topic_stat(s, 90, "strong")
    update_topic_stat(s, 88, "strong")
    assert s.status == "strong"
    d = _decide(stats={"Neural networks": s}, current_topic="Neural networks", last_band="strong", asked=2)
    assert d.topic != "Neural networks"
    assert d.difficulty == "hard"


def test_weak_topic_never_revisited():
    weak = TopicStat(asked=2, scores=[20, 20], weak_streak=2, status="weak")
    stats = {"Neural networks": weak,
             "SQL indexing": TopicStat(asked=2, scores=[60, 60], status="open"),
             "Project: Recommender": TopicStat(asked=2, scores=[65, 65], status="open")}
    for _ in range(3):
        d = _decide(stats=stats, current_topic="SQL indexing", last_band="average", asked=6, question_count=12)
        assert d.topic != "Neural networks"


def test_stops_at_question_count():
    d = _decide(asked=8)
    assert d.action == "complete" and d.stop_reason == "question_count_reached"


def test_stops_at_duration():
    d = _decide(asked=2, elapsed_seconds=1790)
    assert d.action == "complete" and d.stop_reason == "duration_reached"


def test_candidate_end_and_termination():
    assert _decide(candidate_ended=True).stop_reason == "ended_by_candidate"
    assert _decide(terminated=True).stop_reason == "terminated_by_institution"


def test_non_adaptive_keeps_difficulty():
    stats = {"Neural networks": update_topic_stat(TopicStat(), 90, "strong")}
    d = _decide(stats=stats, current_topic="Neural networks", last_band="strong", asked=1, adaptive=False)
    assert d.difficulty == "medium" and d.kind == "new_topic"


def test_coverage_preferred_when_budget_tight():
    # 3 questions, 3 topics: no follow-ups, every topic covered
    stats = {"Neural networks": update_topic_stat(TopicStat(), 62, "average")}
    d = _decide(stats=stats, current_topic="Neural networks", last_band="average", asked=1, question_count=3)
    assert d.kind == "new_topic"


def test_decision_serialisable():
    assert isinstance(_decide().to_dict(), dict) and isinstance(_decide(), Decision)


# ---- evidence-based decisions (criterion scores, confidence and missing concepts from the stored evaluation)
from app.domain.adaptive import AdaptiveConfig, TurnEvidence, read_evidence  # noqa: E402


def _ev(band, overall, correct, complete, depth=5.0, confidence=0.9, missing=()):
    return TurnEvidence(band=band, overall=overall, technical_correctness=correct, completeness=complete, depth=depth,
                        confidence=confidence, missing_concepts=list(missing))


def _decide_ev(ev, **kw):
    stats = {"Neural networks": update_topic_stat(TopicStat(), ev.overall, ev.band)}
    return _decide(stats=stats, current_topic="Neural networks", last_band=ev.band, asked=1, evidence=ev, **kw)


def test_concise_but_correct_answer_is_not_held_back():
    ev = _ev("average", 70, correct=9, complete=8, depth=4)  # short answer: lower overall, but right and complete
    assert read_evidence(ev, AdaptiveConfig())[0] == "concise_correct"
    d = _decide_ev(ev)
    assert d.difficulty == "hard" and d.kind == "follow_up_deeper"


def test_correct_but_incomplete_targets_the_missing_concept():
    d = _decide_ev(_ev("average", 62, correct=7, complete=5, missing=["regularisation", "early stopping"]))
    assert d.kind == "follow_up_gap" and d.difficulty == "medium" and d.focus == ["regularisation", "early stopping"]
    assert "regularisation" in d.reason


def test_vague_answer_gets_a_clarifying_question_not_an_easier_one():
    d = _decide_ev(_ev("weak", 35, correct=3, complete=2, confidence=0.3))
    assert d.kind == "follow_up_clarify" and d.difficulty == "medium"


def test_misconception_gets_a_simpler_diagnostic_question():
    d = _decide_ev(_ev("weak", 25, correct=2, complete=3, confidence=0.9, missing=["bias-variance trade-off"]))
    assert d.kind == "follow_up_foundational" and d.difficulty == "easy" and d.focus == ["bias-variance trade-off"]


def test_same_band_different_evidence_gives_different_next_questions():
    gap = _decide_ev(_ev("average", 60, correct=7, complete=5, missing=["indexes"]))
    probe = _decide_ev(_ev("average", 60, correct=5, complete=6))
    assert gap.kind == "follow_up_gap" and probe.kind == "follow_up_probe"


def test_cut_offs_are_configurable():
    ev = _ev("weak", 40, correct=4, complete=3, confidence=0.55)
    assert _decide_ev(ev).kind == "follow_up_foundational"
    assert _decide_ev(ev, config=AdaptiveConfig(clarify_confidence=0.6)).kind == "follow_up_clarify"
