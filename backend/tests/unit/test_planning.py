from app.domain.planning import build_plan


def test_plan_prioritises_gaps_and_history():
    plan = build_plan(
        interview_type="mixed", question_count=8,
        role_skills=[{"skill": "Python", "skill_key": "python", "importance_weight": 0.6, "topics": ["Python internals"]},
                     {"skill": "SQL", "skill_key": "sql", "importance_weight": 0.6, "topics": ["Database indexing"]}],
        skill_gaps=[{"skill_key": "python", "priority": 0.2}],
        resume_projects=[{"name": "Recommender", "technologies": ["PyTorch"]}],
        historical_weak_topics=["Database indexing"], historical_strong_topics=[],
    )
    topics = [p.topic for p in plan]
    assert topics[0] == "Database indexing"  # historical weakness boosted
    assert "Project: Recommender" in topics
    assert any(p.category == "behavioral" for p in plan)


def test_technical_plan_has_no_behavioral():
    plan = build_plan(interview_type="technical", question_count=5,
                      role_skills=[{"skill": "Go", "skill_key": "go", "importance_weight": 1, "topics": []}],
                      skill_gaps=[], resume_projects=[], historical_weak_topics=[], historical_strong_topics=[])
    assert plan and all(p.category != "behavioral" for p in plan)
