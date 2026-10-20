from datetime import timedelta

from app.core.security import create_token
from tests.conftest import auth, register_institution, register_student


def test_register_login_me_refresh(client):
    inst = register_institution(client)
    assert inst["me"]["role"] == "institution_admin" and inst["code"]
    st = register_student(client, inst["code"])
    assert st["me"]["role"] == "student"
    assert st["me"]["institution_join_code"] is None  # join code never leaked to students
    r = client.post("/auth/login", json={"email": st["me"]["email"], "password": "Password!2345"})
    assert r.status_code == 200 and "ia_refresh" in r.cookies
    r2 = client.post("/auth/refresh")
    assert r2.status_code == 200 and r2.json()["access_token"]


def test_password_is_hashed(client, db):
    from app.models import User

    inst = register_institution(client)
    u = db.get(User, __import__("uuid").UUID(inst["me"]["id"]))
    assert u.password_hash.startswith("$argon2") and "Password" not in u.password_hash


def test_bad_credentials_rejected(client):
    inst = register_institution(client)
    r = client.post("/auth/login", json={"email": inst["me"]["email"], "password": "wrong-password"})
    assert r.status_code == 401


def test_invalid_and_expired_jwt_rejected(client):
    inst = register_institution(client)
    assert client.get("/auth/me", headers=auth("not-a-jwt")).status_code == 401
    import uuid

    expired = create_token(user_id=uuid.UUID(inst["me"]["id"]), role="institution_admin",
                           institute_id=uuid.UUID(inst["me"]["institute_id"]), token_type="access",
                           expires=timedelta(seconds=-10))
    r = client.get("/auth/me", headers=auth(expired))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


def test_refresh_token_cannot_be_used_as_access(client):
    inst = register_institution(client)
    import uuid

    refresh = create_token(user_id=uuid.UUID(inst["me"]["id"]), role="institution_admin",
                           institute_id=uuid.UUID(inst["me"]["institute_id"]), token_type="refresh")
    assert client.get("/auth/me", headers=auth(refresh)).status_code == 401


def test_tampered_role_claim_rejected(client):
    """A student token re-signed with an institution role still fails: role is checked against the DB."""
    inst = register_institution(client)
    st = register_student(client, inst["code"])
    import uuid

    forged = create_token(user_id=uuid.UUID(st["me"]["id"]), role="institution_admin",
                          institute_id=uuid.UUID(st["me"]["institute_id"]), token_type="access")
    assert client.get("/students", headers=auth(forged)).status_code == 401


def test_student_registration_requires_valid_code(client):
    r = client.post("/auth/register", json={"email": "x@example.test", "password": "Password!2345", "full_name": "X",
                                            "account_type": "student", "institution_code": "NOPE"})
    assert r.status_code == 404
