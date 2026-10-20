"""Full lifecycle: resume → eligibility → autonomous interview loop → evaluation → adaptation → report → history."""
import uuid

from tests.conftest import answer_current, create_active_interview, make_docx, register_institution, register_student

RESUME = """Sam Student
Summary
Data science student interested in machine learning.
Education
Synthetic Institute of Technology, B.Tech Data Science
Experience
Example Labs - ML Intern. Built a recommender in Python.
Projects
Movie Recommender: collaborative filtering with PyTorch.
Skills
Python, machine learning, PyTorch, team player
"""


def test_resume_pipeline_grounds_claims(client, _services):
    inst = register_institution(client)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    r = client.post("/resume/upload", headers=st["h"],
                    files={"file": ("cv.docx", make_docx(RESUME), "application/octet-stream")})
    assert r.status_code == 202, r.text
    rid = r.json()["resume"]["id"]
    job = client.get(f"/jobs/{r.json()['job']['id']}", headers=st["h"]).json()
    assert job["status"] == "completed"
    analysis = client.get(f"/resume/{rid}/analysis", headers=st["h"]).json()
    assert analysis["processing_status"] == "completed"
    skills = {s["skill"] for s in analysis["analysis"]["technical_skills"]}
    assert "Python" in skills and "Quantum Basket Weaving" not in skills  # ungrounded claim removed
    assert "Kubernetes-not-in-resume" not in analysis["analysis"]["technologies"]
    assert "skills" in analysis["extraction_meta"]["sections_detected"]
    my_skills = client.get("/skills", headers=st["h"]).json()
    assert any(s["skill"] == "Python" and s["source"] == "resume" for s in my_skills)
    profile = client.get("/profile", headers=st["h"]).json()
    assert profile["projects"][0]["name"] == "Movie Recommender"


def test_resume_rejects_spoofed_file(client):
    inst = register_institution(client)
    st = register_student(client, inst["code"])
    r = client.post("/resume/upload", headers=st["h"], files={"file": ("cv.pdf", b"MZ\x90\x00binary", "application/pdf")})
    assert r.status_code == 422


def test_full_autonomous_interview(client, _services):
    events = _services["events"]
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=4)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    r = client.post(f"/interviews/{iv['id']}/start", headers=st["h"])
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]

    state = client.get(f"/interview/{sid}/state", headers=st["h"]).json()
    assert state["status"] == "in_progress" and state["awaiting"] == "answer"
    q1 = state["current_question"]
    assert q1["sequence"] == 1 and q1["difficulty"] == "medium"
    assert q1["spoken_text"].startswith("Hello Sam")  # AI greets and introduces the interview
    assert any(e["type"] == "question" for e in events)

    # Strong answer → harder follow-up on the same topic
    state = answer_current(client, st, sid, "An excellent detailed explanation of overfitting and validation curves")
    q2 = state["current_question"]
    assert q2["sequence"] == 2 and q2["difficulty"] == "hard" and q2["topic"] == q1["topic"]

    # Weak answer → easier question
    state = answer_current(client, st, sid, "dunno really not sure about this one")
    q3 = state["current_question"]
    assert q3["difficulty"] == "medium"

    # Idempotent retry of the same answer must not duplicate
    key = uuid.uuid4().hex
    body = {"question_id": q3["id"], "transcript": "excellent answer with trade-offs", "idempotency_key": key}
    a1 = client.post(f"/interview/{sid}/answer/text", headers=st["h"], json=body).json()
    a2 = client.post(f"/interview/{sid}/answer/text", headers=st["h"], json=body).json()
    assert a1["answer_id"] == a2["answer_id"] and a2["duplicate"] is True

    state = answer_current(client, st, sid, "excellent final answer covering everything")
    assert state["status"] == "completed"

    result = client.get(f"/interview/{sid}/result", headers=st["h"]).json()
    assert result["overall_score"] is not None and result["readiness"]["level"]
    assert set(result["performance"]["criterion_scores"]) >= {"technical_correctness", "communication"}
    report = client.get(f"/interview/{sid}/report", headers=st["h"]).json()
    c = report["content"]
    assert len(c["questions"]) == 4 and c["summary"] and "guarantee" in c["disclaimer"]
    assert report["export_status"] == "completed" and report["download_url"]
    assert all(q.get("next_question_reason") for q in c["questions"][:3])  # explainability
    qs = client.get(f"/interview/{sid}/questions", headers=st["h"]).json()
    assert qs[0]["evaluation"]["criteria"]["technical_correctness"] == 9
    assert any(e["type"] == "interview_completed" for e in events)

    # dashboards come from real data
    ov = client.get("/overview/student", headers=st["h"]).json()
    assert ov["completed_interviews"] == 1 and ov["score_over_time"]
    io = client.get("/overview/institution", headers=inst["h"]).json()
    assert io["completed_interviews"] == 1 and io["role_performance"][0]["role"] == "AI/ML Engineer"
    hist = client.get("/performance/history", headers=st["h"]).json()
    assert hist[0]["status"] == "completed"

    # cannot retake a completed interview
    assert client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).status_code == 409


def test_history_influences_next_interview(client, _services, db):
    inst = register_institution(client)
    iv1 = create_active_interview(client, inst, question_count=2)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv1['id']}/start", headers=st["h"]).json()["session_id"]
    answer_current(client, st, sid, "dunno at all honestly")
    answer_current(client, st, sid, "dunno again sorry")
    from app.models import InterviewHistory

    h = db.query(InterviewHistory).one()
    assert h.weak_topics  # weakness recorded for future adaptation

    iv2 = create_active_interview(client, inst, question_count=3)
    sid2 = client.post(f"/interviews/{iv2['id']}/start", headers=st["h"]).json()["session_id"]
    from app.models import InterviewSession

    s2 = db.get(InterviewSession, uuid.UUID(sid2))
    db.refresh(s2)
    assert set(h.weak_topics) <= set(s2.state["historical_weak_topics"])
    assert s2.state["plan"][0]["topic"] in h.weak_topics and s2.state["plan"][0]["source"] == "history"
    recs = client.get("/recommendations", headers=st["h"]).json()
    assert recs and any(r["area_type"] in ("topic", "criterion") for r in recs)


def test_candidate_can_end_early_and_institution_can_terminate(client):
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=6)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    answer_current(client, st, sid, "excellent answer")
    assert client.post(f"/interview/{sid}/complete", headers=st["h"]).status_code == 202
    state = client.get(f"/interview/{sid}/state", headers=st["h"]).json()
    assert state["status"] == "completed"
    rep = client.get(f"/interview/{sid}/report", headers=st["h"]).json()
    assert rep["content"]["stop_reason"] == "ended_by_candidate"

    iv2 = create_active_interview(client, inst, role="AI/ML Engineer", question_count=6)
    sid2 = client.post(f"/interviews/{iv2['id']}/start", headers=st["h"]).json()["session_id"]
    mon = client.get(f"/monitoring/sessions/{sid2}", headers=inst["h"]).json()
    assert mon["state"]["status"] == "in_progress" and mon["transcript"][0]["question"]
    assert client.post(f"/monitoring/sessions/{sid2}/terminate", headers=inst["h"]).status_code == 202
    assert client.get(f"/interview/{sid2}/state", headers=st["h"]).json()["status"] == "completed"


def test_audio_answer_goes_through_stt(client, _services):
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=1)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    q = client.get(f"/interview/{sid}/state", headers=st["h"]).json()["current_question"]
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 200  # EBML header signature
    r = client.post(f"/interview/{sid}/answer", headers=st["h"],
                    data={"question_id": q["id"], "idempotency_key": uuid.uuid4().hex},
                    files={"audio": ("a.webm", webm, "audio/webm")})
    assert r.status_code == 202, r.text
    qs = client.get(f"/interview/{sid}/questions", headers=st["h"]).json()
    assert qs[0]["transcript"] == _services["stt"].text
    assert any(k.startswith("interviews/") and "/audio/" in k for k in _services["storage"].objects)


def test_stale_question_answer_rejected(client):
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=3)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    r = client.post(f"/interview/{sid}/answer/text", headers=st["h"],
                    json={"question_id": str(uuid.uuid4()), "transcript": "x y z w", "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 409


def test_interview_ends_by_itself_when_time_is_up(client, db):
    from datetime import timedelta

    from app.models import InterviewSession
    from app.services.runtime import sweep_overdue_sessions

    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=6)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    assert sweep_overdue_sessions(db) == []  # still within the time limit
    s = db.get(InterviewSession, uuid.UUID(sid))
    s.started_at = s.started_at - timedelta(minutes=iv["duration_minutes"], seconds=10)
    db.commit()
    assert sweep_overdue_sessions(db) == [uuid.UUID(sid)]
    assert client.get(f"/interview/{sid}/state", headers=st["h"]).json()["status"] == "completed"
    rep = client.get(f"/interview/{sid}/report", headers=st["h"]).json()
    assert rep["content"]["stop_reason"] == "duration_reached"


def test_browser_transcript_skips_server_stt(client, _services):
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=1)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    q = client.get(f"/interview/{sid}/state", headers=st["h"]).json()["current_question"]
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
    said = "I would split the data into train and validation sets and compare precision and recall"
    r = client.post(f"/interview/{sid}/answer", headers=st["h"],
                    data={"question_id": q["id"], "idempotency_key": uuid.uuid4().hex, "transcript": said},
                    files={"audio": ("a.webm", webm, "audio/webm")})
    assert r.status_code == 202, r.text
    qs = client.get(f"/interview/{sid}/questions", headers=st["h"]).json()
    assert qs[0]["transcript"] == said  # the server STT double was not used
    assert any("/audio/" in k for k in _services["storage"].objects)  # audio still kept


def test_stuck_answer_is_redispatched_at_most_twice(client, db, monkeypatch):
    from datetime import timedelta

    from app.models import Answer, InterviewSession
    from app.services import runtime
    from app.workers import media_tasks

    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=6)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    s = db.get(InterviewSession, uuid.UUID(sid))
    sent = []
    monkeypatch.setattr(media_tasks.process_answer, "apply_async", lambda **kw: sent.append(kw))
    a = Answer(question_id=s.current_question_id, session_id=s.id, candidate_id=s.candidate_id,
               institute_id=s.institute_id, transcript="an answer that got stuck", status="evaluating",
               idempotency_key=uuid.uuid4().hex, meta={})
    db.add(a)
    db.commit()

    def age():  # no progress on the turn for 5 minutes
        db.refresh(a)
        a.updated_at = a.updated_at - timedelta(minutes=5)
        db.commit()

    runtime.sweep_overdue_sessions(db)
    assert sent == []  # recent progress: not stuck
    for _ in range(3):
        age()
        runtime.sweep_overdue_sessions(db)
    assert sent == [{"args": [str(a.id)]}] * 2  # bounded: re-queued twice, then left for the candidate to retry


def test_evaluation_failure_never_invents_a_score_and_can_be_retried(client, _services):
    from app.services.llm import LLMError

    llm = _services["llm"]
    real = llm.handlers["AnswerAssessment"]

    def broken(prompt):
        raise LLMError("provider down")

    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=4)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    llm.handlers["AnswerAssessment"] = broken
    state = answer_current(client, st, sid, "An excellent detailed explanation of overfitting")
    q1 = state["current_question"]
    assert q1["sequence"] == 1  # did not move on without an evaluation
    assert state["turn"]["phase"] == "evaluation_failed" and state["turn"]["retry_allowed"]
    assert state["turn"]["attempts"] == 3  # bounded
    qs = client.get(f"/interview/{sid}/questions", headers=inst["h"]).json()
    assert len(qs) == 1 and qs[0]["evaluation"] is None and qs[0]["answer_status"] == "evaluation_failed"

    llm.handlers["AnswerAssessment"] = real
    r = client.post(f"/interview/{sid}/answer/{state['turn']['answer_id']}/retry", headers=st["h"])
    assert r.status_code == 202
    state = client.get(f"/interview/{sid}/state", headers=st["h"]).json()
    assert state["current_question"]["sequence"] == 2 and state["awaiting"] == "answer"
    qs = client.get(f"/interview/{sid}/questions", headers=inst["h"]).json()
    assert qs[0]["evaluation"]["overall_score"] == 90.0


def test_turn_timeline_proves_order(client, db):
    from app.models import Answer, Evaluation, Question

    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=4)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    answer_current(client, st, sid, "An excellent detailed explanation of overfitting and validation curves")
    answer_current(client, st, sid, "dunno really not sure about this one")
    answers = db.query(Answer).filter(Answer.session_id == uuid.UUID(sid)).all()
    assert len(answers) == 2
    steps = ["answer_finalized", "evaluation_started", "evaluation_completed", "profile_updated",
             "next_question_decided", "next_question_generated", "next_question_presented"]
    for a in answers:
        tl = a.meta["timeline"]
        assert [tl[s] for s in steps] == sorted(tl[s] for s in steps), tl
        ev = db.query(Evaluation).filter(Evaluation.answer_id == a.id).one()
        assert ev.question_id == a.question_id
        q = db.get(Question, a.question_id)
        nxt = db.query(Question).filter(Question.session_id == q.session_id, Question.sequence == q.sequence + 1).one()
        assert nxt.context_meta["decision"]["reason"] == ev.next_question_reason  # decided from this evaluation


def test_answer_in_flight_when_interview_ends_is_scored_in_report(client, _services, monkeypatch):
    from app.workers import media_tasks

    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=4)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    answer_current(client, st, sid, "An excellent detailed explanation of overfitting")
    monkeypatch.setattr(media_tasks.process_answer, "apply_async", lambda **kw: None)  # worker never gets to it
    answer_current(client, st, sid, "dunno really")
    client.post(f"/interview/{sid}/complete", headers=st["h"], json={"reason": "ended_by_candidate"})
    qs = client.get(f"/interview/{sid}/questions", headers=st["h"]).json()
    scores = [q["evaluation"]["overall_score"] for q in qs if q["evaluation"]]
    assert len(scores) == 2  # the last answer is evaluated once at the end, not dropped
    res = client.get(f"/interview/{sid}/result", headers=st["h"]).json()
    assert res["overall_score"] == round(sum(scores) / 2, 2)


def test_speech_to_text_that_hangs_times_out(client, _services, monkeypatch):
    import time as _t

    from app.core.config import get_settings
    from app.services.speech import NullTTS, Transcript, set_speech

    class HangingSTT:
        def transcribe(self, audio, ext):
            _t.sleep(5)
            return Transcript(text="late", language="en", duration_seconds=None, avg_logprob=None)

    monkeypatch.setattr(get_settings(), "stt_timeout_seconds", 1)
    set_speech(HangingSTT(), NullTTS())
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=4)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    q = client.get(f"/interview/{sid}/state", headers=st["h"]).json()["current_question"]
    t0 = _t.monotonic()
    r = client.post(f"/interview/{sid}/answer", headers=st["h"],
                    data={"question_id": q["id"], "idempotency_key": uuid.uuid4().hex},
                    files={"audio": ("a.webm", b"\x1aE\xdf\xa3" + b"\0" * 2000, "audio/webm")})
    assert r.status_code == 202, r.text
    assert _t.monotonic() - t0 < 4  # gave up after the 1 s limit instead of waiting for the stuck model
    state = client.get(f"/interview/{sid}/state", headers=st["h"]).json()
    assert state["awaiting"] == "answer" and state["current_question"]["id"] == q["id"]  # asked to answer again
    assert any(e["type"] == "error" and e["data"].get("retry_allowed") for e in _services["events"])
