"""
NursingStation's read access: the ward-wide roster/dashboard (parity with HeadNurse/Doctor, a
strict superset of what Nurse sees), and read-only access to vitals/tasks/nursing notes/
consultations recorded by other roles -- NursingStation cannot write any of this data itself
(see test_nursingstation_permission_boundaries.py) but must be able to read all of it to do its
front-desk job (answering family questions, coordinating transfers, etc).
"""
import pytest


@pytest.fixture
def station(make_user):
    return make_user(email="station@ns-dashboard.com", role="NursingStation")


@pytest.fixture
def head_nurse(make_user, station):
    return make_user(email="head@ns-dashboard.com", role="HeadNurse", organization_id=station.organization_id)


@pytest.fixture
def nurse(make_user, station):
    return make_user(email="nurse@ns-dashboard.com", role="Nurse", organization_id=station.organization_id)


@pytest.fixture
def doctor(make_user, station):
    return make_user(email="doc@ns-dashboard.com", role="Doctor", organization_id=station.organization_id)


@pytest.fixture
def patient_id(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Read Access Patient", "ward": "General", "bed": "R1"},
                        headers=auth_headers(station))
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Ward-wide roster parity with HeadNurse/Doctor
# ---------------------------------------------------------------------------

def test_station_roster_matches_headnurse_roster_exactly(client, station, head_nurse, auth_headers):
    for i in range(5):
        client.post("/api/ipd/patients", json={"name": f"Parity {i}", "ward": "General", "bed": str(i)},
                    headers=auth_headers(station))
    station_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=auth_headers(station)).json()}
    hn_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()}
    assert station_ids == hn_ids
    assert len(station_ids) == 5


def test_station_sees_abnormal_flag_same_as_headnurse(client, station, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 150}, headers=auth_headers(head_nurse))
    station_view = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    hn_view = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    assert station_view[0]["abnormal"] == hn_view[0]["abnormal"] is True


def test_station_sees_assigned_nurse_info(client, station, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert roster[0]["assigned_nurse"]["email"] == nurse.email


def test_station_sees_unassigned_patients_flagged(client, station, patient_id, auth_headers):
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert roster[0]["assigned_nurse"] is None


def test_station_sees_overdue_tasks_count(client, station, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Late", "due_date": "2020-01-01T10:00:00"},
                headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert roster[0]["overdue_tasks"] == 1


def test_station_sees_pending_tasks_count(client, station, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Task 1"}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Task 2"}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert roster[0]["pending_tasks"] == 2


def test_station_sees_has_nursing_notes_flag(client, station, head_nurse, patient_id, auth_headers):
    client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "x", "objective": "",
                                              "assessment": "", "plan": ""}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert roster[0]["has_nursing_notes"] is True


# ---------------------------------------------------------------------------
# Read-only access to vitals/tasks via the dedicated endpoints
# ---------------------------------------------------------------------------

def test_station_reads_vitals_recorded_by_nurse(client, station, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 78}, headers=auth_headers(nurse))
    vitals = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(station)).json()
    assert len(vitals) == 1
    assert vitals[0]["heart_rate"] == 78


def test_station_reads_tasks_created_by_headnurse(client, station, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Check chart"}, headers=auth_headers(head_nurse))
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(station)).json()
    assert len(tasks) == 1
    assert tasks[0]["description"] == "Check chart"


def test_station_reads_vitals_for_nonexistent_patient_404(client, station, auth_headers):
    resp = client.get("/api/ipd/vitals/999999", headers=auth_headers(station))
    assert resp.status_code == 404


def test_station_reads_tasks_for_nonexistent_patient_404(client, station, auth_headers):
    resp = client.get("/api/ipd/tasks/999999", headers=auth_headers(station))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full chart review via get_patient_details, across every data source (vitals, tasks,
# consultations, nursing notes) regardless of who authored them
# ---------------------------------------------------------------------------

def test_station_reads_full_chart_across_all_recorders(client, station, head_nurse, nurse, doctor, patient_id, auth_headers, db_session):
    from app.models import Consultation

    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 80}, headers=auth_headers(nurse))
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "x"}, headers=auth_headers(head_nurse))
    client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "y", "objective": "",
                                              "assessment": "", "plan": ""}, headers=auth_headers(nurse))
    db_session.add(Consultation(case_id="20260101-abcdef", patient_id=patient_id,
                                 organization_id=station.organization_id, user_id=doctor.id,
                                 chief_complaint="Cough", primary_diagnosis="Bronchitis"))
    db_session.commit()

    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()
    assert len(details["vitals"]) == 1
    assert len(details["tasks"]) == 1
    assert len(details["nursing_notes"]) == 1
    assert len(details["consultations"]) == 1
    assert details["consultations"][0]["primary_diagnosis"] == "Bronchitis"


def test_station_sees_nurse_email_attribution_in_chart(client, station, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 80}, headers=auth_headers(nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()
    assert details["vitals"][0]["nurse_email"] == nurse.email


def test_station_sees_task_overdue_flag_in_chart(client, station, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Late", "due_date": "2020-01-01T10:00:00"},
                headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()
    assert details["tasks"][0]["is_overdue"] is True


def test_station_sees_assigned_nurse_in_patient_details_header(client, station, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(station)).json()
    assert details["patient"]["assigned_nurse"]["email"] == nurse.email
