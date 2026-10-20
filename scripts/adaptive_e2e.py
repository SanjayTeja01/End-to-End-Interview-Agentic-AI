#!/usr/bin/env python
"""End-to-end check of the adaptive interview loop through the real API, worker and LLM.

    docker compose exec backend python /app/scripts/adaptive_e2e.py

It creates a throwaway institution, interview and student, then answers 6 questions with deliberately contrasting
answers (strong, weak, strong, vague, concise-correct, strong). Candidate answers are written by the configured LLM
playing a candidate of that quality, so they actually fit each question. For every turn it prints the server-side
timeline (answer finalised -> evaluation started/completed -> profile updated -> next question decided/presented),
the score, and why the next question was chosen. Finally it checks that the report aggregates exactly the
per-question evaluations. Exit code 0 means every check passed.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time
import uuid

for c in (pathlib.Path(__file__).resolve().parents[1] / "backend", pathlib.Path("/app")):
    if (c / "app").exists():
        sys.path.insert(0, str(c))
        break

import httpx  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

API = os.environ.get("E2E_API", "http://localhost:8000")
PROFILE = ["strong", "weak", "strong", "vague", "concise", "strong"]
TURN_TIMEOUT = float(os.environ.get("E2E_TURN_TIMEOUT", "120"))
STYLE = {
    "strong": "an excellent candidate: correct, complete, with a concrete example and a trade-off, about 90 words",
    "weak": "a weak candidate who is unsure, gets the core idea wrong (state one clear misconception) and gives "
            "no example, about 35 words, starting with 'I think it means' and including 'not sure'",
    "vague": "a candidate who stays vague and generic, never commits to specifics, about 40 words",
    "concise": "a concise expert: fully correct and covers the key points in two short sentences (about 30 words), "
               "no filler",
}


class SimulatedAnswer(BaseModel):
    answer: str = Field(min_length=5, max_length=2000)


def candidate_answer(question: str, style: str) -> str:
    """The simulated candidate shares the interview's LLM quota, so on a rate limit (Groq free tier) it waits."""
    from app.services.llm import LLMError, get_llm

    for attempt in range(6):
        try:
            out = get_llm().generate_structured(
                system="You role-play an interview candidate for an automated test. Reply with JSON only.",
                prompt=f"STYLE: {style}\nAnswer as {STYLE[style]}. Spoken, first person, no lists.\nQUESTION: {question}",
                schema=SimulatedAnswer, temperature=0.7, purpose="e2e_candidate")
            return out.answer
        except LLMError:
            if attempt == 5:
                raise
            print("   (LLM rate limit while writing the test answer; waiting 20 s)")
            time.sleep(20)
    raise RuntimeError("unreachable")


def main() -> int:  # noqa: C901
    c = httpx.Client(base_url=API, timeout=60)
    tag = uuid.uuid4().hex[:8]
    r = c.post("/auth/register", json={"email": f"e2e-admin-{tag}@example.com", "password": "Password!2345",
                                       "full_name": "E2E Admin", "account_type": "institution",
                                       "institution_name": f"E2E Institute {tag}"})
    r.raise_for_status()
    ih = {"Authorization": f"Bearer {r.json()['access_token']}"}
    code = c.get("/auth/me", headers=ih).json()["institution_join_code"]
    skills = [{"skill": "Python", "required_level": 3, "importance_weight": 1.0, "topics": ["Python data structures"]},
              {"skill": "SQL", "required_level": 3, "importance_weight": 0.9, "topics": ["SQL joins and indexing"]},
              {"skill": "REST APIs", "required_level": 3, "importance_weight": 0.8, "topics": ["REST API design"]}]
    r = c.post("/interviews", headers=ih, json={
        "name": f"E2E Backend Interview {tag}", "target_role": "Backend Developer",
        "job_description": "Build backend services in Python with SQL databases and REST APIs.",
        "question_count": len(PROFILE), "duration_minutes": 30, "interview_type": "technical",
        "initial_difficulty": "medium", "adaptive_mode": True, "required_skills": skills, "infer_skills": False})
    r.raise_for_status()
    iid = r.json()["interview"]["id"]
    c.post(f"/interviews/{iid}/activate", headers=ih).raise_for_status()
    r = c.post("/auth/register", json={"email": f"e2e-student-{tag}@example.com", "password": "Password!2345",
                                       "full_name": "Eve Tester", "account_type": "student", "institution_code": code})
    r.raise_for_status()
    sh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    c.put("/profile", headers=sh, json={"target_roles": ["Backend Developer"]}).raise_for_status()
    r = c.post(f"/interviews/{iid}/start", headers=sh)
    r.raise_for_status()
    sid = r.json()["session_id"]
    print(f"session {sid}\n")

    def wait_for_question(prev_id: str | None) -> dict:
        t0 = time.monotonic()
        while time.monotonic() - t0 < TURN_TIMEOUT:
            st = c.get(f"/interview/{sid}/state", headers=sh).json()
            q = st.get("current_question")
            if st["status"] in ("completed", "failed"):
                return st
            if q and q["id"] != prev_id and st["awaiting"] == "answer":
                return st
            time.sleep(0.3)
        raise TimeoutError(f"no new question after {TURN_TIMEOUT}s (last state: {st.get('awaiting')}, "
                           f"turn: {st.get('turn')})")

    failures: list[str] = []
    st = wait_for_question(None)
    prev = None
    for i, style in enumerate(PROFILE, 1):
        q = st["current_question"]
        if not q:
            break
        ans = candidate_answer(q["text"], style)
        t_submit = time.monotonic()
        r = c.post(f"/interview/{sid}/answer/text", headers=sh,
                   json={"question_id": q["id"], "transcript": ans, "idempotency_key": uuid.uuid4().hex})
        r.raise_for_status()
        dup = c.post(f"/interview/{sid}/answer/text", headers=sh,  # duplicate submit must not create a 2nd answer
                     json={"question_id": q["id"], "transcript": ans, "idempotency_key": uuid.uuid4().hex}).json()
        if not dup.get("duplicate"):
            failures.append(f"turn {i}: duplicate submission was not de-duplicated")
        prev = q["id"]
        st = wait_for_question(prev)
        wall = time.monotonic() - t_submit
        print(f"Q{q['sequence']} [{q['difficulty']}, {q['topic']}] answered {style.upper()} -> next question after "
              f"{wall:.1f}s")
        print(f"   Q: {q['text'][:150]}")
        print(f"   A: {ans[:150]}")
        if st["status"] == "completed":
            break

    # ---- per-turn evidence straight from the database
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Answer, Evaluation, InterviewSession, Performance, Question

    db = SessionLocal()
    for _ in range(100):  # the last turn finalises the report
        s = db.get(InterviewSession, uuid.UUID(sid))
        db.refresh(s)
        if s.status == "completed":
            break
        time.sleep(0.5)
        db.expire_all()
    rows = db.execute(select(Question, Answer, Evaluation).outerjoin(Answer, Answer.question_id == Question.id)
                      .outerjoin(Evaluation, Evaluation.answer_id == Answer.id)
                      .where(Question.session_id == uuid.UUID(sid)).order_by(Question.sequence)).all()
    print("\nTimeline (server clock, seconds after the answer was finalised):")
    by_seq = {q.sequence: (q, a, e) for q, a, e in rows}
    scores = []
    for q, a, e in rows:
        if a is None:
            continue
        tl = (a.meta or {}).get("timeline", {})
        base = tl.get("answer_finalized")
        rel = lambda k: f"{tl[k] - base:5.2f}" if base and k in tl else "  -  "  # noqa: E731
        nxt = by_seq.get(q.sequence + 1)
        print(f" Q{q.sequence} answer={a.status:<9} eval_start={rel('evaluation_started')} eval_done={rel('evaluation_completed')}"
              f" profile={rel('profile_updated')} decided={rel('next_question_decided')} presented={rel('next_question_presented')}")
        if e is None:
            failures.append(f"Q{q.sequence}: answer has no evaluation")
            continue
        if e.question_id != q.id or e.answer_id != a.id or e.session_id != q.session_id:
            failures.append(f"Q{q.sequence}: evaluation is linked to the wrong question/answer/session")
        order = [tl.get(k) for k in ("answer_finalized", "evaluation_started", "evaluation_completed",
                                     "profile_updated", "next_question_decided")]
        if None in order or order != sorted(order):
            failures.append(f"Q{q.sequence}: steps out of order or missing: {tl}")
        if nxt and tl.get("next_question_presented") and tl["next_question_presented"] < tl.get("evaluation_completed", 1e18):
            failures.append(f"Q{q.sequence}: next question presented before this evaluation completed")
        if nxt and nxt[0].created_at.timestamp() < e.created_at.timestamp():
            failures.append(f"Q{q.sequence}: next question row created before this evaluation")
        scores.append(e.overall_score)
        nq = nxt[0] if nxt else None
        decision = (nq.context_meta or {}).get("decision", {}) if nq else {}
        print(f"    score {e.overall_score:5.1f} ({e.band}); missing: {', '.join(e.missing_concepts[:3]) or 'none'}")
        if nq:
            print(f"    -> next: {decision.get('kind')} / {nq.difficulty} / {nq.topic}: {decision.get('reason', '')[:160]}")

    # ---- adaptivity checks
    turns = [(by_seq[k][2], by_seq.get(k + 1, (None,))[0]) for k in sorted(by_seq) if by_seq[k][2] is not None]
    kinds = []
    for e, nq in turns:
        if nq is None:
            continue
        d = (nq.context_meta or {}).get("decision", {})
        kinds.append((e.band, d.get("kind"), nq.difficulty, by_seq[nq.sequence - 1][0].difficulty))
    texts = [q.text.strip().lower() for q, _, _ in rows]
    if len(set(texts)) != len(texts):
        failures.append("a question was asked twice")
    if not any(b == "strong" and (k in ("follow_up_deeper", "new_topic") and nd != "easy") for b, k, nd, _ in kinds):
        failures.append("no strong answer led to a deeper/harder next question")
    if not any(b == "weak" and k in ("follow_up_foundational", "follow_up_clarify", "follow_up_gap") for b, k, _, _ in kinds):
        failures.append("no weak answer led to a clarifying/simpler diagnostic question")
    if len({k for _, k, _, _ in kinds}) < 2:
        failures.append("every turn chose the same kind of next question (looks like a fixed sequence)")

    # ---- final report aggregates exactly the per-question evaluations
    perf = db.execute(select(Performance).where(Performance.session_id == uuid.UUID(sid))).scalar_one_or_none()
    counted = [e.overall_score for _, _, e in rows if e is not None and not (e.evidence or {}).get("provisional")]
    if perf is None:
        failures.append("no final performance record")
    else:
        expected = round(sum(counted) / len(counted), 2) if counted else 0.0
        print(f"\nFinal overall score {perf.overall_score} = mean of {len(counted)} evaluated answers ({expected})")
        if abs(perf.overall_score - expected) > 0.01:
            failures.append(f"final score {perf.overall_score} != mean of per-question scores {expected}")
    db.close()

    print("\nRESULT:", "PASS" if not failures else "FAIL")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
