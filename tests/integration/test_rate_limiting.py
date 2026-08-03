"""
Rate limiting on the auth endpoints (register/login/refresh) -- see main.py's
_enforce_rate_limit. Disabled everywhere else in the suite via RATE_LIMIT_ENABLED=false
(tests/conftest.py), since many legitimate tests fire dozens of auth calls from the same
test-client "IP" well within a minute (bulk make_user() fixtures, concurrency tests' 20
simultaneous logins, etc.). These tests explicitly re-enable it to exercise the real behavior.
"""
import pytest

import app.main as app_main


@pytest.fixture(autouse=True)
def _isolated_rate_limit_state(monkeypatch):
    """Enable rate limiting for this file only, with a clean hit-counter each test."""
    monkeypatch.setattr(app_main.settings, "RATE_LIMIT_ENABLED", True)
    app_main._rate_limit_hits.clear()
    yield
    app_main._rate_limit_hits.clear()


def test_login_blocks_after_limit_exceeded_from_same_ip(client, make_user):
    """21 failed logins from one IP: the per-account lockout (5 attempts) kicks in first and
    turns 401 into 403 for a while, but the 21st request must be blocked by the *rate limiter*
    (429) regardless -- it's a separate, IP-scoped defense on top of the account-scoped one."""
    make_user(email="ratelimit-login@example.com", password="Str0ng!Passw0rd#1")
    body = {"email": "ratelimit-login@example.com", "password": "wrong-password"}

    responses = [client.post("/api/auth/login", json=body) for _ in range(21)]

    assert all(r.status_code in (401, 403) for r in responses[:20]), \
        [r.status_code for r in responses[:20]]
    assert responses[20].status_code == 429


def test_login_rate_limit_is_per_endpoint_not_global(client, make_user):
    """Exhausting the login bucket must not also block register/refresh -- separate buckets."""
    make_user(email="ratelimit-scoped@example.com", password="Str0ng!Passw0rd#1")
    for _ in range(20):
        client.post("/api/auth/login", json={
            "email": "ratelimit-scoped@example.com", "password": "wrong-password",
        })
    blocked = client.post("/api/auth/login", json={
        "email": "ratelimit-scoped@example.com", "password": "wrong-password",
    })
    assert blocked.status_code == 429

    register_resp = client.post("/api/auth/register", json={
        "email": "brand-new-user@example.com", "password": "Str0ng!Passw0rd#2",
    })
    assert register_resp.status_code == 200


def test_register_blocks_after_limit_exceeded_from_same_ip(client):
    responses = []
    for i in range(11):
        responses.append(client.post("/api/auth/register", json={
            "email": f"rl-register-{i}@example.com", "password": "Str0ng!Passw0rd#1",
        }))

    assert all(r.status_code == 200 for r in responses[:10]), \
        [(r.status_code, r.text) for r in responses[:10]]
    assert responses[10].status_code == 429


def test_refresh_blocks_after_limit_exceeded_from_same_ip(client, make_user, auth_headers):
    user = make_user(email="ratelimit-refresh@example.com")
    from app.auth import create_refresh_token
    token_data = {"user_id": user.id, "email": user.email, "role": user.role, "organization_id": user.organization_id}
    refresh_token = create_refresh_token(token_data)

    responses = [client.post("/api/auth/refresh", json={"refresh_token": refresh_token}) for _ in range(31)]

    assert all(r.status_code == 200 for r in responses[:30]), \
        [(r.status_code, r.text) for r in responses[:30]]
    assert responses[30].status_code == 429


def test_rate_limiting_disabled_by_default_in_test_suite(client, monkeypatch):
    """Sanity check for every other test file in the suite: with the default test env
    (RATE_LIMIT_ENABLED=false), bursts of auth calls are never blocked."""
    monkeypatch.setattr(app_main.settings, "RATE_LIMIT_ENABLED", False)
    responses = [client.post("/api/auth/register", json={
        "email": f"no-limit-{i}@example.com", "password": "Str0ng!Passw0rd#1",
    }) for i in range(15)]
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
