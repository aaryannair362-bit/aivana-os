"""
Patient administrative-record management by NursingStation: updating ward/bed/diagnosis,
discharge/transfer, and the interplay between station-driven administrative changes and
clinical state (assignments, vitals, tasks) that other roles manage.
"""
import pytest


@pytest.fixture
def station(make_user):
    return make_user(email="station@ns-patient-mgmt.com", role="NursingStation")


@pytest.fixture
def head_nurse(make_user, station):
    return make_user(email="head@ns-patient-mgmt.com", role="HeadNurse", organization_id=station.organization_id)


@pytest.fixture
def nurse(make_user, station):
    return make_user(email="nurse@ns-patient-mgmt.com", role="Nurse", organization_id=station.organization_id)


@pytest.fixture
def patient_id(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "PM Patient", "ward": "General", "bed": "P1"},
                        headers=auth_headers(station))
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Administrative updates
# ---------------------------------------------------------------------------

def test_station_updates_ward_and_bed_on_transfer(client, station, patient_id, auth_headers):
    resp = client.put(f"/api/patients/{patient_id}", json={"ward": "ICU", "bed": "ICU-2"}, headers=auth_headers(station))
    assert resp.status_code == 200
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()
    assert details["patient"]["ward"] == "ICU"
    assert details["patient"]["bed"] == "ICU-2"


def test_station_updates_diagnosis_after_initial_assessment(client, station, patient_id, auth_headers):
    resp = client.put(f"/api/patients/{patient_id}", json={"diagnosis": "Confirmed: acute appendicitis"},
                       headers=auth_headers(station))
    assert resp.status_code == 200


def test_station_partial_update_leaves_other_fields_untouched(client, station, patient_id, auth_headers):
    client.put(f"/api/patients/{patient_id}", json={"ward": "ICU"}, headers=auth_headers(station))
    before = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()["patient"]
    client.put(f"/api/patients/{patient_id}", json={"bed": "ICU-9"}, headers=auth_headers(station))
    after = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()["patient"]
    assert after["ward"] == "ICU"  # preserved from the first update
    assert after["bed"] == "ICU-9"


def test_station_updates_same_patient_multiple_times_in_one_shift(client, station, patient_id, auth_headers):
    updates = [{"ward": "Emergency"}, {"ward": "General"}, {"bed": "G5"}, {"diagnosis": "Stable, monitoring"}]
    for u in updates:
        resp = client.put(f"/api/patients/{patient_id}", json=u, headers=auth_headers(station))
        assert resp.status_code == 200
    final = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()["patient"]
    assert final["ward"] == "General"
    assert final["bed"] == "G5"
    assert final["diagnosis"] == "Stable, monitoring"


# ---------------------------------------------------------------------------
# Discharge/transfer processing
# ---------------------------------------------------------------------------

def test_station_discharges_a_patient(client, station, patient_id, auth_headers):
    resp = client.put(f"/api/patients/{patient_id}", json={"status": "Discharged"}, headers=auth_headers(station))
    assert resp.status_code == 200
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert patient_id not in [p["id"] for p in roster]


def test_station_discharge_closes_active_nurse_assignment(client, station, head_nurse, nurse, patient_id, auth_headers, db_session):
    from app.models import NurseAssignment
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.put(f"/api/patients/{patient_id}", json={"status": "Discharged"}, headers=auth_headers(station))
    assignment = db_session.query(NurseAssignment).filter(NurseAssignment.patient_id == patient_id).first()
    assert assignment.status == "Completed"


def test_station_processes_transfer_to_another_facility(client, station, patient_id, auth_headers):
    resp = client.put(f"/api/patients/{patient_id}", json={"status": "Transferred"}, headers=auth_headers(station))
    assert resp.status_code == 200
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert patient_id not in [p["id"] for p in roster]


def test_station_can_reactivate_a_discharged_patient(client, station, patient_id, auth_headers):
    """Documents current behavior: status is freely settable back to Active, e.g. a
    re-admission or a discharge processed in error."""
    client.put(f"/api/patients/{patient_id}", json={"status": "Discharged"}, headers=auth_headers(station))
    resp = client.put(f"/api/patients/{patient_id}", json={"status": "Active"}, headers=auth_headers(station))
    assert resp.status_code == 200
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert patient_id in [p["id"] for p in roster]


def test_station_discharges_one_of_several_patients_without_affecting_others(client, station, auth_headers):
    s = auth_headers(station)
    ids = [client.post("/api/ipd/patients", json={"name": f"Multi {i}", "ward": "General", "bed": str(i)},
                        headers=s).json()["id"] for i in range(4)]
    client.put(f"/api/patients/{ids[1]}", json={"status": "Discharged"}, headers=s)
    roster_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=s).json()}
    assert ids[0] in roster_ids
    assert ids[1] not in roster_ids
    assert ids[2] in roster_ids
    assert ids[3] in roster_ids


def test_discharged_patient_still_reviewable_by_station_for_records(client, station, patient_id, auth_headers):
    client.put(f"/api/patients/{patient_id}", json={"status": "Discharged"}, headers=auth_headers(station))
    resp = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station))
    assert resp.status_code == 200
    assert resp.json()["patient"]["status"] == "Discharged"


# ---------------------------------------------------------------------------
# Cannot discharge/edit a patient it has no organizational access to
# ---------------------------------------------------------------------------

def test_station_cannot_update_other_orgs_patient(client, station, make_user, db_session, auth_headers):
    from app.models import Patient
    other_station = make_user(email="other-station@ns-patient-mgmt.com", role="NursingStation")
    patient = Patient(name="Foreign Patient", ward="General", bed="F1",
                       organization_id=other_station.organization_id, created_by=other_station.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    resp = client.put(f"/api/patients/{patient.id}", json={"status": "Discharged"}, headers=auth_headers(station))
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Station's edits are visible to (and don't conflict with) HeadNurse's concurrent clinical
# management of the same patient
# ---------------------------------------------------------------------------

def test_station_and_headnurse_edits_to_same_patient_both_persist(client, station, head_nurse, patient_id, auth_headers):
    client.put(f"/api/patients/{patient_id}", json={"ward": "ICU"}, headers=auth_headers(station))
    client.put(f"/api/patients/{patient_id}", json={"diagnosis": "Updated by head nurse"}, headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()["patient"]
    assert details["ward"] == "ICU"
    assert details["diagnosis"] == "Updated by head nurse"


def test_station_admits_headnurse_assigns_nurse_records_vitals_station_discharges(client, station, head_nurse, nurse, auth_headers):
    """Full cross-role lifecycle: the realistic division of labor across all three ward roles
    for a single patient's stay, start to finish."""
    s = auth_headers(station)
    pid = client.post("/api/ipd/patients", json={"name": "Full Lifecycle Patient", "ward": "General", "bed": "L1"},
                       headers=s).json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 74}, headers=auth_headers(nurse))
    discharge = client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=s)
    assert discharge.status_code == 200
    details = client.get(f"/api/patients/{pid}/details", headers=s).json()
    assert details["patient"]["status"] == "Discharged"
    assert len(details["vitals"]) == 1
