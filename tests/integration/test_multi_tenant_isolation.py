"""
Multi-tenant isolation tests for the IPD module.

AIVANA is a multi-tenant system: ARCHITECTURE_NOTES.md documents that every clinical row
(Patient, Vital, Task, NursingNote) carries an organization_id (directly or via the patient
it belongs to). These tests check that staff at Organization A can never see or modify
Organization B's patients through the IPD endpoints -- a cross-tenant leak here is a PHI
exposure incident in a real deployment, not a cosmetic bug.
"""
import pytest


@pytest.fixture
def two_orgs(make_user, db_session):
    """Two separate organizations, each with a HeadNurse, a Nurse, and one admitted patient."""
    from app.models import Patient

    org_a_head = make_user(email="head.a@hosp-a.com", role="HeadNurse")
    org_b_head = make_user(email="head.b@hosp-b.com", role="HeadNurse")

    patient_a = Patient(name="Patient A", age=40, gender="F", ward="A-Ward", bed="A1",
                         diagnosis="Org A condition", organization_id=org_a_head.organization_id,
                         created_by=org_a_head.id)
    patient_b = Patient(name="Patient B", age=50, gender="M", ward="B-Ward", bed="B1",
                         diagnosis="Org B condition", organization_id=org_b_head.organization_id,
                         created_by=org_b_head.id)
    db_session.add_all([patient_a, patient_b])
    db_session.commit()
    db_session.refresh(patient_a)
    db_session.refresh(patient_b)

    return {
        "org_a_head": org_a_head, "org_b_head": org_b_head,
        "patient_a": patient_a, "patient_b": patient_b,
    }


def test_get_ipd_patients_does_not_leak_other_orgs_patients(client, two_orgs, auth_headers):
    """
    Regression test: GET /api/ipd/patients (main.py:584-629) filters only on
    Patient.status == "Active" for HeadNurse/NursingStation/Doctor callers, with no
    organization_id filter -- so Org A's HeadNurse would see Org B's patient roster too.
    """
    resp = client.get("/api/ipd/patients", headers=auth_headers(two_orgs["org_a_head"]))
    assert resp.status_code == 200
    seen_ids = {p["id"] for p in resp.json()}
    assert two_orgs["patient_a"].id in seen_ids
    assert two_orgs["patient_b"].id not in seen_ids, (
        "Org A HeadNurse can see Org B's patient in the IPD roster -- cross-tenant PHI leak"
    )


def test_get_patient_details_blocks_cross_org_access(client, two_orgs, auth_headers):
    """
    GET /api/patients/{id}/details (main.py:428-504) looks up Patient by id alone with no
    organization_id check -- an IDOR letting any HeadNurse/NursingStation/Doctor fetch any
    other org's patient record (vitals, tasks, nursing notes, consultations included) just by
    guessing/incrementing the numeric id.
    """
    resp = client.get(
        f"/api/patients/{two_orgs['patient_b'].id}/details",
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404), (
        f"Org A HeadNurse fetched Org B's patient details cross-tenant (got {resp.status_code})"
    )


def test_update_patient_blocks_cross_org_modification(client, two_orgs, auth_headers):
    """PUT /api/patients/{id} (main.py:506-530) must not let Org A modify Org B's patient."""
    resp = client.put(
        f"/api/patients/{two_orgs['patient_b'].id}",
        json={"diagnosis": "tampered by wrong org"},
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)


def test_assign_patient_blocks_cross_org_assignment(client, two_orgs, auth_headers, make_user):
    """
    POST /api/ipd/assign (main.py:652-671) must not let Org A's HeadNurse assign a nurse
    (from either org) to Org B's patient.
    """
    org_a_nurse = make_user(email="nurse.a@hosp-a.com", role="Nurse",
                             organization_id=two_orgs["org_a_head"].organization_id)
    resp = client.post(
        "/api/ipd/assign",
        json={"patient_id": two_orgs["patient_b"].id, "nurse_id": org_a_nurse.id},
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)


def test_record_vital_blocks_cross_org_head_nurse(client, two_orgs, auth_headers):
    """
    POST /api/ipd/vitals (main.py:673-711): the is_nurse() branch checks NurseAssignment,
    but a HeadNurse caller has no equivalent org/patient check at all.
    """
    resp = client.post(
        "/api/ipd/vitals",
        json={"patient_id": two_orgs["patient_b"].id, "bp_systolic": 120, "bp_diastolic": 80,
              "heart_rate": 70, "temperature": 37.0, "oxygen_sat": 98, "respiratory_rate": 16},
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)


def test_get_vitals_blocks_cross_org_access(client, two_orgs, auth_headers):
    resp = client.get(
        f"/api/ipd/vitals/{two_orgs['patient_b'].id}",
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)


def test_create_task_blocks_cross_org_patient(client, two_orgs, auth_headers):
    resp = client.post(
        "/api/ipd/tasks",
        json={"patient_id": two_orgs["patient_b"].id, "description": "cross-org task injection"},
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)


def test_get_tasks_blocks_cross_org_access(client, two_orgs, auth_headers):
    resp = client.get(
        f"/api/ipd/tasks/{two_orgs['patient_b'].id}",
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)


def test_create_nursing_note_blocks_cross_org_patient(client, two_orgs, auth_headers):
    resp = client.post(
        "/api/nursing-notes",
        json={"patient_id": two_orgs["patient_b"].id, "subjective": "x", "objective": "x",
              "assessment": "x", "plan": "x"},
        headers=auth_headers(two_orgs["org_a_head"]),
    )
    assert resp.status_code in (403, 404)
