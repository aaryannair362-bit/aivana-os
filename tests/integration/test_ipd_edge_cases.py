"""
Boundary, missing-field, and business-invariant edge cases for the IPD module
(backend/app/main.py). See ARCHITECTURE_NOTES.md section 5 for the abnormal-vital
threshold rule and the "single active assignment" invariant this file pins down.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@ipd-edge.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@ipd-edge.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post(
        "/api/ipd/patients",
        json={"name": "Edge Case Patient", "ward": "General", "bed": "B1"},
        headers=auth_headers(head_nurse),
    )
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Missing/malformed required fields (main.py: create_ipd_patient, assign_patient,
# create_task, record_vital) -- regression tests for the 400-instead-of-500 fix.
# ---------------------------------------------------------------------------

def test_create_patient_missing_name_rejected_cleanly(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"ward": "General"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_create_patient_missing_ward_rejected_cleanly(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "No Ward"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_assign_patient_missing_nurse_id_rejected_cleanly(client, head_nurse, auth_headers, patient_id):
    resp = client.post("/api/ipd/assign", json={"patient_id": patient_id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_assign_nonexistent_patient_returns_404_not_500(client, head_nurse, nurse, auth_headers):
    resp = client.post(
        "/api/ipd/assign", json={"patient_id": 999999, "nurse_id": nurse.id},
        headers=auth_headers(head_nurse),
    )
    assert resp.status_code == 404


def test_create_task_missing_description_rejected_cleanly(client, head_nurse, auth_headers, patient_id):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_create_task_invalid_due_date_rejected_cleanly_not_500(client, head_nurse, auth_headers, patient_id):
    resp = client.post(
        "/api/ipd/tasks",
        json={"patient_id": patient_id, "description": "Check vitals", "due_date": "not-a-date"},
        headers=auth_headers(head_nurse),
    )
    assert resp.status_code == 400


def test_create_task_valid_due_date_accepted(client, head_nurse, auth_headers, patient_id):
    resp = client.post(
        "/api/ipd/tasks",
        json={"patient_id": patient_id, "description": "Check vitals", "due_date": "2026-08-01T10:00:00"},
        headers=auth_headers(head_nurse),
    )
    assert resp.status_code == 200


def test_record_vital_missing_patient_id_rejected_cleanly(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"bp_systolic": 120}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_record_vital_for_nonexistent_patient_returns_404(client, head_nurse, auth_headers):
    resp = client.post(
        "/api/ipd/vitals", json={"patient_id": 999999, "bp_systolic": 120},
        headers=auth_headers(head_nurse),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Abnormal-vital flagging boundaries (main.py get_ipd_patients:
# bp_systolic > 140 OR bp_diastolic > 90 OR heart_rate > 100 OR temperature > 38).
# Strict "greater than" -- exact threshold values must NOT be flagged.
# ---------------------------------------------------------------------------

def _record_vital(client, auth_headers, head_nurse, patient_id, **vitals):
    payload = {"patient_id": patient_id, "bp_systolic": 110, "bp_diastolic": 70,
               "heart_rate": 70, "temperature": 37.0, "oxygen_sat": 98, "respiratory_rate": 16}
    payload.update(vitals)
    resp = client.post("/api/ipd/vitals", json=payload, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    return resp


def _is_flagged(client, auth_headers, head_nurse, patient_id):
    patients = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in patients if p["id"] == patient_id)
    return p["abnormal"]


@pytest.mark.parametrize("field,boundary,above", [
    ("bp_systolic", 140, 141),
    ("bp_diastolic", 90, 91),
    ("heart_rate", 100, 101),
    ("temperature", 38.0, 38.1),
])
def test_abnormal_vital_boundary_exact_value_not_flagged(client, auth_headers, head_nurse, patient_id, field, boundary, above):
    _record_vital(client, auth_headers, head_nurse, patient_id, **{field: boundary})
    assert _is_flagged(client, auth_headers, head_nurse, patient_id) is False, (
        f"{field}={boundary} (exactly the threshold) was flagged abnormal; rule is strict '>'"
    )


@pytest.mark.parametrize("field,boundary,above", [
    ("bp_systolic", 140, 141),
    ("bp_diastolic", 90, 91),
    ("heart_rate", 100, 101),
    ("temperature", 38.0, 38.1),
])
def test_abnormal_vital_boundary_just_above_is_flagged(client, auth_headers, head_nurse, patient_id, field, boundary, above):
    _record_vital(client, auth_headers, head_nurse, patient_id, **{field: above})
    assert _is_flagged(client, auth_headers, head_nurse, patient_id) is True


def test_patient_with_no_vitals_recorded_is_not_flagged_abnormal(client, auth_headers, head_nurse, patient_id):
    assert _is_flagged(client, auth_headers, head_nurse, patient_id) is False


def test_negative_vital_values_are_accepted_without_validation(client, auth_headers, head_nurse, patient_id):
    """
    Documents current behavior (see TEST_NOTES.md "vital range validation"): a physiologically
    impossible negative heart rate is stored as-is and, since the abnormal check only tests
    for values ABOVE a high threshold, is never flagged -- a negative or zero vital silently
    passes through as "normal". This is a known gap, not silently patched with an invented
    valid-range, since the codebase defines no canonical physiological bounds.
    """
    resp = _record_vital(client, auth_headers, head_nurse, patient_id, heart_rate=-10, bp_systolic=-50)
    assert resp.status_code == 200
    assert _is_flagged(client, auth_headers, head_nurse, patient_id) is False


# ---------------------------------------------------------------------------
# Single-active-assignment invariant (documented in ARCHITECTURE_NOTES.md section 5):
# assigning a new nurse must close out the prior Active assignment for that patient.
# ---------------------------------------------------------------------------

def test_reassigning_patient_closes_prior_active_assignment(client, auth_headers, head_nurse, make_user, patient_id):
    from app.models import NurseAssignment

    nurse_1 = make_user(email="nurse1@ipd-edge.com", role="Nurse", organization_id=head_nurse.organization_id)
    nurse_2 = make_user(email="nurse2@ipd-edge.com", role="Nurse", organization_id=head_nurse.organization_id)

    r1 = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse_1.id},
                      headers=auth_headers(head_nurse))
    assert r1.status_code == 200
    r2 = client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse_2.id},
                      headers=auth_headers(head_nurse))
    assert r2.status_code == 200

    # Only nurse_2 should have visibility into the patient now.
    nurse1_patients = client.get("/api/ipd/patients", headers=auth_headers(nurse_1)).json()
    nurse2_patients = client.get("/api/ipd/patients", headers=auth_headers(nurse_2)).json()
    assert patient_id not in [p["id"] for p in nurse1_patients]
    assert patient_id in [p["id"] for p in nurse2_patients]
