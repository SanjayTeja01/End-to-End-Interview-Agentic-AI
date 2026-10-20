"""An institution admin can permanently remove a student together with everything recorded about them."""
import uuid

from sqlalchemy import func, select

from tests.conftest import answer_current, create_active_interview, make_docx, register_institution, register_student
from tests.integration.test_interview_e2e import RESUME


def test_admin_removes_student_and_all_their_data(client, _services, db):
    from app.models import Answer, Evaluation, FileObject, InterviewSession, Performance, Resume, User

    storage = _services["storage"]
    inst = register_institution(client)
    iv = create_active_interview(client, inst, question_count=4)
    st = register_student(client, inst["code"], ["AI/ML Engineer"])
    keep = register_student(client, inst["code"], ["AI/ML Engineer"])
    assert client.post("/resume/upload", headers=st["h"],
                       files={"file": ("cv.docx", make_docx(RESUME), "application/octet-stream")}).status_code == 202
    sid = client.post(f"/interviews/{iv['id']}/start", headers=st["h"]).json()["session_id"]
    answer_current(client, st, sid, "An excellent detailed explanation of overfitting")

    # Not while the interview is still running
    r = client.delete(f"/students/{st['me']['id']}", headers=inst["h"])
    assert r.status_code == 409, r.text
    assert client.post(f"/interview/{sid}/complete", headers=st["h"]).status_code == 202

    sid_u = uuid.UUID(st["me"]["id"])
    keys = list(db.execute(select(FileObject.object_key).where(FileObject.owner_id == sid_u)).scalars())
    assert keys and all(storage.exists(k) for k in keys)

    # Students cannot remove anyone; another institution cannot see this student
    assert client.delete(f"/students/{keep['me']['id']}", headers=st["h"]).status_code == 403
    other = register_institution(client, "Other Institute")
    assert client.delete(f"/students/{st['me']['id']}", headers=other["h"]).status_code == 404

    assert client.delete(f"/students/{st['me']['id']}", headers=inst["h"]).status_code == 204
    db.expire_all()
    assert db.get(User, sid_u) is None
    for model, col in ((InterviewSession, InterviewSession.candidate_id), (Answer, Answer.candidate_id),
                       (Evaluation, Evaluation.candidate_id), (Performance, Performance.candidate_id),
                       (Resume, Resume.candidate_id), (FileObject, FileObject.owner_id)):
        assert db.execute(select(func.count()).select_from(model).where(col == sid_u)).scalar_one() == 0, model
    assert not any(storage.exists(k) for k in keys)
    assert client.post("/auth/login", json={"email": st["me"]["email"], "password": "Password!2345"}).status_code == 401

    listed = client.get("/students", headers=inst["h"]).json()
    assert [s["id"] for s in listed["items"]] == [keep["me"]["id"]]
    assert client.delete(f"/students/{st['me']['id']}", headers=inst["h"]).status_code == 404
