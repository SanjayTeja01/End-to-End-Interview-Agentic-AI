"""Explicit security tests: cross-tenant and cross-candidate access must fail for manually constructed requests."""
import uuid

import pytest

from tests.conftest import answer_current, create_active_interview, make_docx, register_institution, register_student


@pytest.fixture
def world(client):
    a = register_institution(client, "Institute A")
    b = register_institution(client, "Institute B")
    iv_a = create_active_interview(client, a, question_count=1)
    s1 = register_student(client, a["code"], ["AI/ML Engineer"])
    s2 = register_student(client, a["code"], ["AI/ML Engineer"])
    sb = register_student(client, b["code"], ["AI/ML Engineer"])
    r = client.post("/resume/upload", headers=s1["h"], files={"file": ("cv.docx", make_docx("Skills\nPython"), "x")})
    resume_id = r.json()["resume"]["id"]
    sid = client.post(f"/interviews/{iv_a['id']}/start", headers=s1["h"]).json()["session_id"]
    answer_current(client, s1, sid, "excellent answer")
    doc = client.post("/knowledge/documents", headers=a["h"], data={"title": "A secret guide", "document_type": "technical",
                                                                     "role": "AI/ML Engineer"},
                      files={"file": ("g.txt", b"Institute A confidential overfitting rubric text.", "text/plain")}).json()
    return {"a": a, "b": b, "iv_a": iv_a, "s1": s1, "s2": s2, "sb": sb, "resume_id": resume_id, "sid": sid,
            "doc_id": doc["document"]["id"]}


def test_institution_cannot_read_other_institution_data(client, world):
    b, w = world["b"], world
    assert client.get(f"/interviews/{w['iv_a']['id']}", headers=b["h"]).status_code == 404
    assert client.get(f"/students/{w['s1']['me']['id']}", headers=b["h"]).status_code == 404
    assert client.get(f"/interview/{w['sid']}/report", headers=b["h"]).status_code == 404
    assert client.get(f"/monitoring/sessions/{w['sid']}", headers=b["h"]).status_code == 404
    assert client.post(f"/monitoring/sessions/{w['sid']}/terminate", headers=b["h"]).status_code == 404
    assert client.get(f"/knowledge/documents/{w['doc_id']}", headers=b["h"]).status_code == 404
    assert client.get(f"/resume/{w['resume_id']}", headers=b["h"]).status_code == 404
    assert client.get("/students", headers=b["h"]).json()["total"] == 1  # only its own student
    assert all(i["id"] != w["iv_a"]["id"] for i in client.get("/interviews", headers=b["h"]).json())


def test_institution_cannot_retrieve_other_tenant_rag(client, world):
    hits = client.post("/rag/query", headers=world["b"]["h"], json={"query": "confidential overfitting rubric"}).json()
    assert hits == []
    own = client.post("/rag/query", headers=world["a"]["h"], json={"query": "confidential overfitting rubric"}).json()
    assert own and all(h["metadata"]["institute_id"] == world["a"]["me"]["institute_id"] for h in own)


def test_student_cannot_access_other_student_data(client, world):
    s2, w = world["s2"], world
    assert client.get(f"/resume/{w['resume_id']}", headers=s2["h"]).status_code == 404
    assert client.get(f"/resume/{w['resume_id']}/download", headers=s2["h"]).status_code == 404
    assert client.get(f"/interview/{w['sid']}/report", headers=s2["h"]).status_code == 404
    assert client.get(f"/interview/{w['sid']}/result", headers=s2["h"]).status_code == 404
    assert client.get(f"/interview/{w['sid']}/state", headers=s2["h"]).status_code == 404
    r = client.post(f"/interview/{w['sid']}/answer/text", headers=s2["h"],
                    json={"question_id": str(uuid.uuid4()), "transcript": "hijack attempt", "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 404


def test_student_cannot_use_institution_endpoints(client, world):
    s1 = world["s1"]
    for method, path in (("get", "/students"), ("get", "/knowledge/documents"), ("get", "/overview/institution"),
                         ("post", "/rag/query"), ("get", f"/monitoring/interviews/{world['iv_a']['id']}"),
                         ("post", f"/interviews/{world['iv_a']['id']}/activate")):
        kwargs = {"json": {"query": "x y"}} if path == "/rag/query" else {}
        assert getattr(client, method)(path, headers=s1["h"], **kwargs).status_code == 403, path
    r = client.post("/interviews", headers=s1["h"], json={"name": "x", "target_role": "y", "infer_skills": True})
    assert r.status_code == 403


def test_student_of_other_institution_cannot_join(client, world):
    sb = world["sb"]
    assert client.post(f"/interviews/{world['iv_a']['id']}/start", headers=sb["h"]).status_code == 404
    assert client.get(f"/interview/{world['sid']}/state", headers=sb["h"]).status_code == 404


def test_unauthenticated_requests_rejected(client, world):
    for path in ("/interviews", "/students", f"/interview/{world['sid']}/report", "/profile", "/overview/student"):
        assert client.get(path).status_code == 401


def test_presigned_urls_require_authorisation(client, world):
    own = client.get(f"/resume/{world['resume_id']}/download", headers=world["s1"]["h"])
    assert own.status_code == 200 and "expires=" in own.json()["url"]
    inst = client.get(f"/resume/{world['resume_id']}/download", headers=world["a"]["h"])
    assert inst.status_code == 200  # own institution's candidate
    assert client.get(f"/resume/{world['resume_id']}/download", headers=world["b"]["h"]).status_code == 404


def test_object_keys_are_tenant_prefixed(world, _services):
    inst_a = world["a"]["me"]["institute_id"]
    keys = list(_services["storage"].objects)
    assert keys and all(k.split("/")[1] == inst_a for k in keys)


def test_websocket_rejects_unauthenticated_and_foreign_users(client, world):
    with client.websocket_connect(f"/ws/interview/{world['sid']}") as ws:
        ws.send_json({"type": "auth", "token": "garbage", "role": "candidate"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
    with client.websocket_connect(f"/ws/interview/{world['sid']}") as ws:
        ws.send_json({"type": "auth", "token": world["s2"]["token"], "role": "candidate"})
        assert ws.receive_json()["type"] == "error"
    with client.websocket_connect(f"/ws/interview/{world['sid']}") as ws:
        ws.send_json({"type": "auth", "token": world["b"]["token"], "role": "monitor"})
        assert ws.receive_json()["type"] == "error"
    with client.websocket_connect(f"/ws/interview/{world['sid']}") as ws:
        ws.send_json({"type": "auth", "token": world["s1"]["token"], "role": "monitor"})  # student can't monitor
        assert ws.receive_json()["type"] == "error"


def test_vector_query_without_tenant_is_impossible():
    from rag.retrieval.vector_store import InMemoryVectorStore, TenantFilterMissing

    with pytest.raises(TenantFilterMissing):
        InMemoryVectorStore().query([0.1], institute_id="", filters=None, k=3)
