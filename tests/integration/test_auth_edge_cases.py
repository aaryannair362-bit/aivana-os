"""
Auth-flow edge cases: login lockout boundary, admin password reset (regression test for the
query-string -> JSON-body fix), and a documented email-case-sensitivity ambiguity.
"""
import pytest


PASSWORD = "Str0ng!Passw0rd#1"


@pytest.fixture
def user(make_user):
    return make_user(email="locktest@example.com", password=PASSWORD, role="Admin")


def _bad_login(client, email):
    return client.post("/api/auth/login", json={"email": email, "password": "WrongPassword123!"})


def test_account_not_locked_after_4_failed_attempts(client, user):
    for _ in range(4):
        resp = _bad_login(client, user.email)
        assert resp.status_code == 401
    # 5th attempt with the correct password should still succeed.
    resp = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 200


def test_account_locked_on_5th_failed_attempt(client, user):
    for _ in range(5):
        resp = _bad_login(client, user.email)
    assert resp.status_code == 403
    assert "locked" in resp.json()["detail"].lower()
    # Even the correct password must now be rejected while locked.
    resp = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 403


def test_login_nonexistent_email_returns_generic_invalid_credentials(client):
    """Must not reveal whether the email exists (e.g. distinguish from a wrong-password 401)."""
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123!"})
    assert resp.status_code == 401
    assert "invalid credentials" in resp.json()["detail"].lower()


def test_login_missing_password_field_rejected_cleanly(client, user):
    resp = client.post("/api/auth/login", json={"email": user.email})
    assert resp.status_code == 400


@pytest.mark.xfail(
    reason="Documents an ambiguity (see TEST_NOTES.md 'email case sensitivity'): User.email "
           "has a unique constraint but lookups/inserts do no case-folding, so 'a@x.com' and "
           "'A@x.com' are treated as distinct identities. Not silently fixed since normalizing "
           "email casing is an auth-identity decision, flagged for the product owner instead.",
    strict=False,
)
def test_registration_is_case_insensitive_for_duplicate_email(client, user):
    resp = client.post("/api/auth/register", json={
        "email": user.email.upper(), "password": "Zk9#mQ4!vXyLp2Q",
    })
    assert resp.status_code == 400, "expected duplicate-email rejection regardless of case"


def test_admin_reset_password_via_json_body_succeeds(client, user, auth_headers):
    """Regression test for the reset_user_password query-string-password fix (main.py)."""
    new_password = "Br4nd#NewSecurePw9"
    resp = client.patch(
        f"/api/auth/users/{user.id}/password",
        json={"new_password": new_password},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    login = client.post("/api/auth/login", json={"email": user.email, "password": new_password})
    assert login.status_code == 200


def test_admin_reset_password_rejects_weak_password(client, user, auth_headers):
    resp = client.patch(
        f"/api/auth/users/{user.id}/password",
        json={"new_password": "weak"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400


def test_admin_reset_password_missing_field_rejected_cleanly(client, user, auth_headers):
    resp = client.patch(f"/api/auth/users/{user.id}/password", json={}, headers=auth_headers(user))
    assert resp.status_code == 400
