from tests.conftest import SKILLS, create_active_interview, register_institution, register_student


def test_provided_skills_are_approved_and_activatable(client):
    inst = register_institution(client)
    iv = create_active_interview(client, inst)
    assert iv["status"] == "active" and iv["skill_approval_state"] == "not_required"
    assert {s["skill"] for s in iv["skills"]} == {"Machine Learning", "Python"}


def test_inferred_skills_require_approval_before_activation(client):
    inst = register_institution(client)
    r = client.post("/interviews", headers=inst["h"], json={
        "name": "Agentic AI", "target_role": "Agentic AI Engineer", "job_description": "LLM agents", "infer_skills": True})
    assert r.status_code == 201
    body = r.json()
    iid = body["interview"]["id"]
    assert body["job"]["job_type"] == "skill_inference"
    detail = client.get(f"/interviews/{iid}", headers=inst["h"]).json()
    assert detail["status"] == "pending_approval" and detail["skill_approval_state"] == "pending"
    assert all(s["source"] == "ai_inferred" and s["approval_status"] == "pending" for s in detail["skills"])
    assert detail["skills"][0]["rationale"]

    # cannot activate before approval
    r = client.post(f"/interviews/{iid}/activate", headers=inst["h"])
    assert r.status_code == 409

    # institution edits (adds a skill) — still pending
    edited = [*[{k: s[k] for k in ("skill", "required_level", "importance_weight", "topics")} for s in detail["skills"]],
              {"skill": "Prompt engineering", "required_level": 3, "importance_weight": 0.6, "topics": ["Prompt design"]}]
    r = client.put(f"/interviews/{iid}/skills", headers=inst["h"], json={"skills": edited})
    assert r.status_code == 200 and r.json()["skill_approval_state"] == "pending" and len(r.json()["skills"]) == 3

    r = client.post(f"/interviews/{iid}/approve", headers=inst["h"])
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["skill_approval_state"] == "approved"
    r = client.post(f"/interviews/{iid}/activate", headers=inst["h"])
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_requires_skills_or_inference(client):
    inst = register_institution(client)
    r = client.post("/interviews", headers=inst["h"], json={"name": "X", "target_role": "Y", "infer_skills": False})
    assert r.status_code == 422


def test_invalid_rubric_weights_rejected(client):
    inst = register_institution(client)
    r = client.post("/interviews", headers=inst["h"], json={
        "name": "X", "target_role": "Y", "required_skills": SKILLS,
        "evaluation_config": {"rubric_weights": {"technical_correctness": 1}}})
    assert r.status_code == 422


def test_active_interview_cannot_be_edited_or_reactivated(client):
    inst = register_institution(client)
    iv = create_active_interview(client, inst)
    assert client.put(f"/interviews/{iv['id']}", headers=inst["h"], json={"question_count": 3}).status_code == 409
    assert client.post(f"/interviews/{iv['id']}/activate", headers=inst["h"]).status_code == 409


def test_future_start_schedules(client):
    from datetime import datetime, timedelta, timezone

    inst = register_institution(client)
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post("/interviews", headers=inst["h"], json={"name": "Later", "target_role": "AI/ML Engineer",
                                                            "required_skills": SKILLS, "start_time": start})
    iid = r.json()["interview"]["id"]
    r = client.post(f"/interviews/{iid}/activate", headers=inst["h"])
    assert r.json()["status"] == "scheduled"
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    listed = client.get("/interviews", headers=st["h"]).json()
    assert listed and listed[0]["joinable"] is False
    assert client.post(f"/interviews/{iid}/start", headers=st["h"]).status_code == 403


def test_eligibility_role_filtering(client):
    inst = register_institution(client)
    ml = create_active_interview(client, inst, role="AI/ML Engineer")
    devops = create_active_interview(client, inst, role="DevOps Engineer")
    st = register_student(client, inst["code"], ["AI/ML Engineer", "Agentic AI Engineer"])
    visible = {i["id"] for i in client.get("/interviews", headers=st["h"]).json()}
    assert ml["id"] in visible and devops["id"] not in visible
    # Constructing the request manually does not bypass backend eligibility
    assert client.post(f"/interviews/{devops['id']}/start", headers=st["h"]).status_code == 403
    assert client.get(f"/interviews/{devops['id']}", headers=st["h"]).status_code == 404


def test_assignment_and_revocation(client):
    inst = register_institution(client)
    iv = create_active_interview(client, inst, role="DevOps Engineer", eligibility_config={"mode": "assigned_only"})
    st = register_student(client, inst["code"], ["DevOps Engineer"])
    assert client.get("/interviews", headers=st["h"]).json() == []
    client.post(f"/interviews/{iv['id']}/candidates", headers=inst["h"], json={"candidate_ids": [st["me"]["id"]]})
    assert [i["id"] for i in client.get("/interviews", headers=st["h"]).json()] == [iv["id"]]
    client.post(f"/interviews/{iv['id']}/candidates", headers=inst["h"],
                json={"candidate_ids": [st["me"]["id"]], "action": "revoke"})
    assert client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).status_code == 403


def test_interview_stats_and_listing(client):
    inst = register_institution(client)
    create_active_interview(client, inst)
    register_student(client, inst["code"], ["AI/ML Engineer"])
    rows = client.get("/interviews", headers=inst["h"]).json()
    assert rows[0]["stats"]["candidate_count"] == 1
