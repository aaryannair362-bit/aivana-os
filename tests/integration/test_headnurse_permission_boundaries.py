"""
Everything a HeadNurse must NOT be able to do -- admin-only actions, OPD/doctor-only actions,
and malformed/adversarial input specifically as the HeadNurse actor. Complements
test_role_permission_matrix.py's broader 5-role sweep with HeadNurse-focused depth.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-boundaries.com", role="HeadNurse")


@pytest.fixture
def target_user(make_user, head_nurse):
    return make_user(email="target@hn-boundaries.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Boundary Patient", "ward": "General", "bed": "B1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Admin-only actions HeadNurse must never reach
# ---------------------------------------------------------------------------

def test_headnurse_cannot_change_a_users_role(client, head_nurse, target_user, auth_headers):
    resp = client.patch(f"/api/auth/users/{target_user.id}", json={"role": "HeadNurse"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 403


def test_headnurse_cannot_reset_a_users_password(client, head_nurse, target_user, auth_headers):
    resp = client.patch(f"/api/auth/users/{target_user.id}/password", json={"new_password": "NewStr0ng!Passw0rd9"},
                         headers=auth_headers(head_nurse))
    assert resp.status_code == 403


def test_headnurse_cannot_create_users_via_admin_endpoint(client, head_nurse, auth_headers):
    resp = client.post("/api/auth/admin/create-user", json={"email": "sneaky@hn-boundaries.com",
                                                              "password": "NewStr0ng!Passw0rd9", "role": "Nurse"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 403


def test_headnurse_can_still_view_users_list_admin_privilege_exception(client, head_nurse, auth_headers):
    """GET /api/auth/users is the one Admin-adjacent endpoint HeadNurse IS allowed -- needed to
    populate the nurse-assignment dropdown. Confirms this specific carve-out, not a blanket denial."""
    resp = client.get("/api/auth/users", headers=auth_headers(head_nurse))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# HeadNurse-only endpoints must not be reachable by role-tampering the request itself (the
# role comes from the JWT payload, not the request body -- confirm a body-level role override
# attempt does nothing).
# ---------------------------------------------------------------------------

def test_role_field_in_request_body_cannot_escalate_headnurse_to_admin(client, head_nurse, auth_headers):
    resp = client.post("/api/auth/admin/create-user",
                        json={"email": "x@hn-boundaries.com", "password": "NewStr0ng!Passw0rd9",
                              "role": "Nurse", "current_user_role_override": "Admin"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Malformed / adversarial input specifically as HeadNurse -- confirms the fixes from earlier
# passes (400-not-500, coercion) hold up under this specific actor too.
# ---------------------------------------------------------------------------

def test_headnurse_admit_missing_name_rejected(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"ward": "General"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_headnurse_assign_to_nonexistent_nurse_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": 999999}, headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_headnurse_assign_malformed_json_body_rejected_cleanly(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/assign", content=b"{not valid json",
                        headers={**auth_headers(head_nurse), "Content-Type": "application/json"})
    assert resp.status_code == 400


def test_headnurse_create_task_malformed_due_date_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "x", "due_date": "not-a-date"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 400


@pytest.mark.parametrize("patient_id_value", [None, "", 0, -1, "abc", [], {}])
def test_headnurse_assign_various_malformed_patient_ids_never_500(client, head_nurse, target_user, auth_headers, patient_id_value):
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id_value, "nurse_id": target_user.id}, headers=auth_headers(head_nurse))
    assert resp.status_code in (400, 404, 422), f"patient_id={patient_id_value!r} produced {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("nurse_id_value", [None, "", 0, -1, "abc", [], {}, 3.5])
def test_headnurse_assign_various_malformed_nurse_ids_never_500(client, head_nurse, patient_id, auth_headers, nurse_id_value):
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse_id_value}, headers=auth_headers(head_nurse))
    assert resp.status_code in (400, 404, 422), f"nurse_id={nurse_id_value!r} produced {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# A HeadNurse cannot assign a Nurse from a DIFFERENT organization to their own org's patient,
# even with a perfectly valid-looking nurse_id (the ID just belongs to someone else's org).
# ---------------------------------------------------------------------------

def test_headnurse_cannot_assign_cross_org_nurse(client, head_nurse, patient_id, auth_headers, make_user):
    foreign_nurse = make_user(email="foreign-nurse@hn-boundaries.com", role="Nurse")
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": foreign_nurse.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_headnurse_cannot_assign_a_doctor_as_if_they_were_a_nurse(client, head_nurse, patient_id, auth_headers, make_user):
    doctor = make_user(email="doc@hn-boundaries.com", role="Doctor", organization_id=head_nurse.organization_id)
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": doctor.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_headnurse_cannot_assign_another_headnurse_as_if_they_were_a_nurse(client, head_nurse, patient_id, auth_headers, make_user):
    other_head = make_user(email="other-head@hn-boundaries.com", role="HeadNurse", organization_id=head_nurse.organization_id)
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": other_head.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session / token edge cases specific to the HeadNurse actor
# ---------------------------------------------------------------------------

def test_expired_headnurse_access_token_rejected(client, head_nurse):
    from datetime import datetime, timedelta
    from jose import jwt as jose_jwt
    from app.config import settings

    token_data = {"user_id": head_nurse.id, "email": head_nurse.email, "role": "HeadNurse",
                  "organization_id": head_nurse.organization_id}
    expired = jose_jwt.encode({**token_data, "exp": datetime.utcnow() - timedelta(minutes=1), "type": "access"},
                               settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    resp = client.get("/api/ipd/patients", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client, head_nurse):
    login = client.post("/api/auth/login", json={"email": head_nurse.email, "password": "Str0ng!Passw0rd#1"}).json()
    resp = client.get("/api/ipd/patients", headers={"Authorization": f"Bearer {login['refresh_token']}"})
    assert resp.status_code == 401


def test_tampered_role_claim_in_token_does_not_grant_admin(client, head_nurse):
    """A token whose payload was hand-crafted to claim role=Admin, but signed with the wrong
    key, must be rejected outright (signature verification, not just payload trust)."""
    from jose import jwt as jose_jwt

    forged = jose_jwt.encode(
        {"user_id": head_nurse.id, "email": head_nurse.email, "role": "Admin",
         "organization_id": head_nurse.organization_id, "type": "access"},
        "wrong-secret-key", algorithm="HS256",
    )
    resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Deactivated/locked HeadNurse account cannot act even with a still-valid token minted before
# lockout (documents current behavior: get_current_user only decodes the JWT, it never
# re-checks the user's live status in the DB).
# ---------------------------------------------------------------------------

def test_locked_headnurse_with_still_valid_token_can_still_call_api(client, head_nurse, auth_headers, db_session):
    """Documents current behavior: JWTs are stateless and not re-validated against live user
    status per-request, so a token minted before an account lock remains usable for its full
    lifetime. Not fixed here -- revoking live tokens on lock/deactivation is a larger session-
    management feature (a token blocklist or short-lived tokens + server-side session state),
    not a one-line patch, and is a product decision about acceptable exposure window."""
    from app.models import User
    token = auth_headers(head_nurse)
    user = db_session.query(User).filter(User.id == head_nurse.id).first()
    user.status = "Locked"
    db_session.commit()
    resp = client.get("/api/ipd/patients", headers=token)
    assert resp.status_code == 200
