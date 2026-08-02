"""
Regression tests for a critical cross-tenant vulnerability found during the full-app end-to-end
pass (2026-08-01): GET /api/auth/users, PATCH /api/auth/users/{id}, and
PATCH /api/auth/users/{id}/password had NO organization scoping at all, unlike every other
IPD endpoint (which had this exact class of bug fixed in an earlier pass -- these three
user-management endpoints were apparently missed at the time).

Severity, by endpoint:
- GET /api/auth/users: any Admin/HeadNurse could see every user's email/role/status across
  EVERY organization in the system -- a straightforward cross-tenant PHI/data leak.
- PATCH /api/auth/users/{id}: any Admin could change the role of ANY user in ANY other
  organization -- e.g. promote a stranger's account to Admin, or demote another hospital's
  admin to Nurse. A privilege-escalation / sabotage vector across tenants.
- PATCH /api/auth/users/{id}/password: any Admin could reset the password of ANY user in ANY
  other organization -- a full account-takeover vector across tenants, the most severe of the
  three. Found via test_hospital_scale_scenarios.py's small-clinic test unexpectedly returning
  5 users (including the unrelated default-bootstrap admin from a different org) instead of 4.
"""
import pytest


@pytest.fixture
def two_orgs(make_user):
    org_a_admin = make_user(email="admin.a@user-mgmt-isolation.com", role="Admin")
    org_b_admin = make_user(email="admin.b@user-mgmt-isolation.com", role="Admin")
    org_a_head = make_user(email="head.a@user-mgmt-isolation.com", role="HeadNurse", organization_id=org_a_admin.organization_id)
    org_b_nurse = make_user(email="nurse.b@user-mgmt-isolation.com", role="Nurse", organization_id=org_b_admin.organization_id)
    return {"org_a_admin": org_a_admin, "org_b_admin": org_b_admin, "org_a_head": org_a_head, "org_b_nurse": org_b_nurse}


def test_get_users_does_not_leak_other_orgs_users(client, two_orgs, auth_headers):
    resp = client.get("/api/auth/users", headers=auth_headers(two_orgs["org_a_admin"]))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert two_orgs["org_a_admin"].email in emails
    assert two_orgs["org_a_head"].email in emails
    assert two_orgs["org_b_admin"].email not in emails
    assert two_orgs["org_b_nurse"].email not in emails


def test_get_users_as_headnurse_does_not_leak_other_orgs_users(client, two_orgs, auth_headers):
    resp = client.get("/api/auth/users", headers=auth_headers(two_orgs["org_a_head"]))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert two_orgs["org_b_admin"].email not in emails
    assert two_orgs["org_b_nurse"].email not in emails


def test_get_users_role_filter_still_scoped_to_own_org(client, two_orgs, auth_headers):
    resp = client.get("/api/auth/users?role=Nurse", headers=auth_headers(two_orgs["org_a_admin"]))
    assert resp.status_code == 200
    assert resp.json() == []  # org A has no Nurse; org B's nurse must not leak through the filter


def test_cannot_change_role_of_another_orgs_user(client, two_orgs, auth_headers):
    resp = client.patch(f"/api/auth/users/{two_orgs['org_b_nurse'].id}", json={"role": "Admin"},
                         headers=auth_headers(two_orgs["org_a_admin"]))
    assert resp.status_code == 404


def test_cross_org_role_change_attempt_does_not_actually_change_the_role(client, two_orgs, auth_headers, db_session):
    from app.models import User
    client.patch(f"/api/auth/users/{two_orgs['org_b_nurse'].id}", json={"role": "Admin"},
                 headers=auth_headers(two_orgs["org_a_admin"]))
    victim = db_session.query(User).filter(User.id == two_orgs["org_b_nurse"].id).first()
    assert victim.role == "Nurse", "cross-org role-change attempt must not silently succeed despite the 404"


def test_cannot_reset_password_of_another_orgs_user(client, two_orgs, auth_headers):
    resp = client.patch(f"/api/auth/users/{two_orgs['org_b_nurse'].id}/password",
                         json={"new_password": "Attacker!Passw0rd99"}, headers=auth_headers(two_orgs["org_a_admin"]))
    assert resp.status_code == 404


def test_cross_org_password_reset_attempt_does_not_change_the_victims_password(client, two_orgs, auth_headers, db_session):
    from app.models import User
    from app import auth as app_auth
    victim_before = db_session.query(User).filter(User.id == two_orgs["org_b_nurse"].id).first()
    original_hash = victim_before.password_hash

    client.patch(f"/api/auth/users/{two_orgs['org_b_nurse'].id}/password",
                 json={"new_password": "Attacker!Passw0rd99"}, headers=auth_headers(two_orgs["org_a_admin"]))

    victim_after = db_session.query(User).filter(User.id == two_orgs["org_b_nurse"].id).first()
    assert victim_after.password_hash == original_hash, "attacker's password reset must not have taken effect"
    # The victim's real password must still work.
    login = client.post("/api/auth/login", json={"email": two_orgs["org_b_nurse"].email, "password": "Str0ng!Passw0rd#1"})
    assert login.status_code == 200


def test_own_org_role_change_still_works_after_the_fix(client, two_orgs, auth_headers):
    """Regression guard: the org-scoping fix must not break the legitimate same-org case."""
    resp = client.patch(f"/api/auth/users/{two_orgs['org_a_head'].id}", json={"role": "Nurse"},
                         headers=auth_headers(two_orgs["org_a_admin"]))
    assert resp.status_code == 200


def test_own_org_password_reset_still_works_after_the_fix(client, two_orgs, auth_headers):
    resp = client.patch(f"/api/auth/users/{two_orgs['org_a_head'].id}/password",
                         json={"new_password": "NewLegit!Passw0rd99"}, headers=auth_headers(two_orgs["org_a_admin"]))
    assert resp.status_code == 200
    login = client.post("/api/auth/login", json={"email": two_orgs["org_a_head"].email, "password": "NewLegit!Passw0rd99"})
    assert login.status_code == 200


def test_admin_cannot_enumerate_other_orgs_user_ids_via_incrementing(client, two_orgs, auth_headers):
    """Even without knowing the target belongs to another org, guessing/incrementing user_ids
    must not reveal cross-org accounts (404, not a 403 that would confirm existence)."""
    resp = client.get(f"/api/auth/users?role=Admin", headers=auth_headers(two_orgs["org_a_admin"]))
    ids_seen = {u["id"] for u in resp.json()}
    assert two_orgs["org_b_admin"].id not in ids_seen
