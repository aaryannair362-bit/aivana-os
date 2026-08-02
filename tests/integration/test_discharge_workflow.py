"""
Discharge/transfer workflow tests.

Before this fix there was no discharge workflow at all in the frontend (PUT /api/patients/{id}
only ever received ward/bed/diagnosis from the UI, never status), and even via direct API use,
setting status away from "Active" never closed the patient's active NurseAssignment -- so a
discharged patient with a never-closed assignment kept appearing in that nurse's ward list
forever. Both gaps are fixed: the UI now has a Discharge action, and PUT /api/patients/{id}
cascades any status change away from "Active" into closing the active assignment.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@discharge.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@discharge.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def assigned_patient(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Discharge Patient", "ward": "General", "bed": "D1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


def test_discharge_closes_active_nurse_assignment(client, head_nurse, nurse, assigned_patient, auth_headers, db_session):
    from app.models import NurseAssignment
    resp = client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assignment = db_session.query(NurseAssignment).filter(NurseAssignment.patient_id == assigned_patient).first()
    assert assignment.status == "Completed"


def test_discharged_patient_disappears_from_nurses_ward_list(client, head_nurse, nurse, assigned_patient, auth_headers):
    client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    nurse_patients = client.get("/api/ipd/patients", headers=auth_headers(nurse)).json()
    assert assigned_patient not in [p["id"] for p in nurse_patients]


def test_discharged_patient_disappears_from_head_nurse_active_roster(client, head_nurse, assigned_patient, auth_headers):
    client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    assert assigned_patient not in [p["id"] for p in roster]


def test_discharged_patient_chart_still_accessible_for_records(client, head_nurse, nurse, assigned_patient, auth_headers):
    """Discharge must not make the historical chart unreachable -- get_patient_details has no
    Active-status filter, so head nurse/nursing station/doctor can still pull up the record."""
    client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    resp = client.get(f"/api/patients/{assigned_patient}/details", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert resp.json()["patient"]["status"] == "Discharged"


def test_discharged_patient_no_longer_visible_to_previously_assigned_nurse_details(client, head_nurse, nurse, assigned_patient, auth_headers):
    """Once discharged, the assignment is closed, so the (former) nurse loses the assignment-
    based access path to patient details -- this is expected, not a bug."""
    client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    resp = client.get(f"/api/patients/{assigned_patient}/details", headers=auth_headers(nurse))
    assert resp.status_code == 403


def test_transfer_status_also_closes_assignment(client, head_nurse, nurse, assigned_patient, auth_headers, db_session):
    """Any non-Active status (not just literally "Discharged") should close the assignment --
    e.g. transferring a patient to another ward/facility."""
    from app.models import NurseAssignment
    resp = client.put(f"/api/patients/{assigned_patient}", json={"status": "Transferred"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assignment = db_session.query(NurseAssignment).filter(NurseAssignment.patient_id == assigned_patient).first()
    assert assignment.status == "Completed"


def test_setting_status_to_active_does_not_error_with_no_prior_assignment_change(client, head_nurse, assigned_patient, auth_headers):
    """Re-affirming status="Active" (a no-op discharge-cancel) must not error or touch assignments."""
    resp = client.put(f"/api/patients/{assigned_patient}", json={"status": "Active"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_re_admitting_after_discharge_does_not_restore_old_assignment(client, head_nurse, nurse, assigned_patient, auth_headers, db_session):
    """Documents current behavior: flipping status back to Active does not resurrect the closed
    assignment -- the patient becomes Active again but unassigned, requiring an explicit
    re-assign. This is intentional (avoids silently re-attaching a possibly-unavailable nurse)."""
    from app.models import NurseAssignment
    client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    client.put(f"/api/patients/{assigned_patient}", json={"status": "Active"}, headers=auth_headers(head_nurse))
    nurse_patients = client.get("/api/ipd/patients", headers=auth_headers(nurse)).json()
    assert assigned_patient not in [p["id"] for p in nurse_patients]
    active_assignments = db_session.query(NurseAssignment).filter(
        NurseAssignment.patient_id == assigned_patient, NurseAssignment.status == "Active"
    ).count()
    assert active_assignments == 0


def test_discharge_patient_with_no_prior_assignment_does_not_error(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Never Assigned Patient", "ward": "General", "bed": "D2"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    discharge_resp = client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    assert discharge_resp.status_code == 200


def test_nursing_station_can_discharge(client, make_user, head_nurse, assigned_patient, auth_headers):
    station = make_user(email="station@discharge.com", role="NursingStation", organization_id=head_nurse.organization_id)
    resp = client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(station))
    assert resp.status_code == 200


def test_nurse_cannot_discharge(client, nurse, assigned_patient, auth_headers):
    resp = client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(nurse))
    assert resp.status_code == 403


def test_discharging_one_patient_does_not_affect_another_nurses_other_patients(client, head_nurse, nurse, assigned_patient, auth_headers):
    resp2 = client.post("/api/ipd/patients", json={"name": "Second Patient", "ward": "General", "bed": "D3"},
                         headers=auth_headers(head_nurse))
    pid2 = resp2.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid2, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))

    client.put(f"/api/patients/{assigned_patient}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))

    nurse_patients = client.get("/api/ipd/patients", headers=auth_headers(nurse)).json()
    ids = [p["id"] for p in nurse_patients]
    assert pid2 in ids
    assert assigned_patient not in ids
