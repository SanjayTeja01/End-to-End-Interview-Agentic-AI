"""Test harness: SQLite + in-memory doubles for MinIO/Chroma/Gemini/STT/TTS, Celery in eager mode.

The doubles implement the same interfaces as production services, so API, agents, LangGraph and
tenant-isolation logic are exercised end-to-end without external infrastructure.
Integration tests against the real Docker stack are marked `integration`.
"""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "JWT_SECRET": "test-secret-" + "x" * 40,
    "CELERY_EAGER": "true",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "LLM_PROVIDER": "scripted",
    "CORS_ORIGINS": "http://testserver,http://localhost:3000",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import realtime  # noqa: E402
from app.services.llm import LLMService, ScriptedProvider, set_llm  # noqa: E402
from app.services.speech import NullTTS, StaticSTT, set_speech  # noqa: E402
from rag.embeddings.providers import HashEmbeddings, set_embeddings  # noqa: E402
from rag.retrieval.vector_store import InMemoryVectorStore, set_vector_store  # noqa: E402
from storage.minio.client import InMemoryStorage, set_storage  # noqa: E402

if engine.dialect.name == "sqlite":  # enforce ON DELETE CASCADE / RESTRICT like PostgreSQL does
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_fks(conn, _record):  # noqa: ANN001
        conn.execute("PRAGMA foreign_keys=ON")


# ------------------------------------------------------------------ scripted LLM
def _resume_analysis(prompt: str) -> dict:
    return {
        "education": [{"institution": "Synthetic Institute of Technology", "degree": "B.Tech", "field": "Data Science"}],
        "experience": [{"organization": "Example Labs", "title": "ML Intern", "highlights": ["Built a recommender"]}],
        "projects": [{"name": "Movie Recommender", "description": "Collaborative filtering recommender",
                      "technologies": ["Python", "PyTorch"], "highlights": []}],
        "technical_skills": [
            {"skill": "Python", "estimated_level": 4, "evidence": "Python", "confidence": 0.8},
            {"skill": "Machine Learning", "estimated_level": 3, "evidence": "machine learning", "confidence": 0.7},
            {"skill": "Quantum Basket Weaving", "estimated_level": 5, "evidence": "invented claim", "confidence": 0.9},
        ],
        "non_technical_skills": [{"skill": "Teamwork", "estimated_level": 3, "evidence": "team", "confidence": 0.5}],
        "technologies": ["Python", "PyTorch", "Kubernetes-not-in-resume"],
        "certifications": [], "achievements": [], "role_evidence": [], "summary": "Data science student.",
    }


ROLE_REQS = {"skills": [
    {"skill": "Machine Learning", "required_level": 4, "importance": 5, "topics": ["Model evaluation", "Overfitting"],
     "question_categories": ["conceptual", "applied"], "rationale": "JD requires ML"},
    {"skill": "Python", "required_level": 3, "importance": 4, "topics": ["Python data structures"],
     "question_categories": ["applied"], "rationale": "JD requires Python"},
]}


class QuestionWriter:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self, prompt: str) -> dict:
        self.n += 1
        topic = re.search(r"Topic: (.*?) \|", prompt)
        diff = re.search(r"Difficulty: (\w+)", prompt)
        return {"question": f"Q{self.n} [{diff.group(1) if diff else '?'}] Explain {topic.group(1) if topic else 'it'} please?",
                "spoken_transition": "Next question.", "expected_points": ["point a", "point b"]}


def _assess(prompt: str) -> dict:
    answer = prompt.split("CANDIDATE ANSWER", 1)[1].lower()
    level = 9 if "excellent" in answer else 2 if "dunno" in answer else 6
    return {c: level for c in ("technical_correctness", "relevance", "completeness", "clarity", "depth", "communication")} | {
        "confidence": 0.8, "strengths": [{"point": "Mentions concepts", "evidence_quote": "excellent"}] if level == 9 else [],
        "weaknesses": [] if level == 9 else [{"point": "Lacks depth", "evidence_quote": ""}],
        "missing_concepts": [] if level == 9 else ["bias-variance trade-off"],
        "improvement_actions": ["Give an example"], "suggested_answer_structure": "Define, apply, trade-offs",
        "practice_topics": ["Overfitting"], "rationale": f"Scored {level}/10 on the provided answer."}


@pytest.fixture(autouse=True)
def _services():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    storage, vectors = InMemoryStorage(), InMemoryVectorStore()
    set_storage(storage)
    set_vector_store(vectors)
    set_embeddings(HashEmbeddings())
    provider = ScriptedProvider({
        "ResumeAnalysis": _resume_analysis, "RoleRequirements": ROLE_REQS, "GeneratedQuestion": QuestionWriter(),
        "AnswerAssessment": _assess,
        "ReportNarrative": {"summary": "Synthetic summary.", "final_assessment": "Synthetic assessment."},
    })
    set_llm(LLMService(provider))
    stt = StaticSTT("an excellent answer about overfitting and validation")
    set_speech(stt, NullTTS())
    events = realtime.capture_events(True)
    yield {"storage": storage, "vectors": vectors, "llm": provider, "stt": stt, "events": events}
    realtime.capture_events(False)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


# ------------------------------------------------------------------ helpers
def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_institution(client, name: str = "Synthetic Institute") -> dict:
    email = f"admin-{uuid.uuid4().hex[:8]}@example.test"
    r = client.post("/auth/register", json={"email": email, "password": "Password!2345", "full_name": "Admin User",
                                            "account_type": "institution", "institution_name": name})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers=auth(token)).json()
    return {"token": token, "h": auth(token), "me": me, "code": me["institution_join_code"]}


def register_student(client, code: str, roles: list[str] | None = None) -> dict:
    email = f"student-{uuid.uuid4().hex[:8]}@example.test"
    r = client.post("/auth/register", json={"email": email, "password": "Password!2345", "full_name": "Sam Student",
                                            "account_type": "student", "institution_code": code})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    h = auth(token)
    if roles:
        assert client.put("/profile", json={"target_roles": roles}, headers=h).status_code == 200
    me = client.get("/auth/me", headers=h).json()
    return {"token": token, "h": h, "me": me}


def make_docx(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


SKILLS = [{"skill": "Machine Learning", "required_level": 4, "importance_weight": 1.0, "topics": ["Overfitting", "Model evaluation"]},
          {"skill": "Python", "required_level": 3, "importance_weight": 0.8, "topics": ["Python data structures"]}]


def create_active_interview(client, inst: dict, *, role: str = "AI/ML Engineer", question_count: int = 4,
                            interview_type: str = "technical", **extra) -> dict:
    body = {"name": f"{role} Interview", "target_role": role, "job_description": "Build ML systems in Python.",
            "question_count": question_count, "duration_minutes": 30, "interview_type": interview_type,
            "required_skills": SKILLS, **extra}
    r = client.post("/interviews", json=body, headers=inst["h"])
    assert r.status_code == 201, r.text
    iid = r.json()["interview"]["id"]
    r = client.post(f"/interviews/{iid}/activate", headers=inst["h"])
    assert r.status_code == 200, r.text
    return r.json()


def answer_current(client, student: dict, session_id: str, transcript: str) -> dict:
    st = client.get(f"/interview/{session_id}/state", headers=student["h"]).json()
    q = st["current_question"]
    r = client.post(f"/interview/{session_id}/answer/text", headers=student["h"],
                    json={"question_id": q["id"], "transcript": transcript, "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 202, r.text
    return client.get(f"/interview/{session_id}/state", headers=student["h"]).json()


__all__ = ["auth", "register_institution", "register_student", "make_docx", "create_active_interview", "answer_current", "json"]
