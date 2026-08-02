"""
Dashboard/roster data correctness for HeadNurse under realistic busy-ward compositions --
combinations of abnormal vitals, overdue tasks, and assignment state together (the three
signals the new ward-summary stat bar and priority sorting in frontend/ipd.html's loadDashboard
depend on), which the more narrowly-scoped feature test files don't exercise in combination.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-dashboard.com", role="HeadNurse")


@pytest.fixture
def nurses(make_user, head_nurse):
    return [make_user(email=f"nurse{i}@hn-dashboard.com", role="Nurse", organization_id=head_nurse.organization_id)
            for i in range(3)]


def _admit(client, auth_headers, head_nurse, **overrides):
    payload = {"name": "Dashboard Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(head_nurse))
    return resp.json()["id"]


def test_empty_ward_dashboard(client, head_nurse, auth_headers):
    resp = client.get("/api/ipd/patients", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert resp.json() == []


def test_dashboard_with_one_of_every_state_combination(client, head_nurse, nurses, auth_headers):
    """Four patients covering all four combinations of {abnormal, overdue} x {assigned,
    unassigned} -- confirms each signal is computed independently and correctly, not coupled."""
    h = auth_headers(head_nurse)

    normal_assigned = _admit(client, auth_headers, head_nurse, name="Normal Assigned", bed="1")
    client.post("/api/ipd/assign", json={"patient_id": normal_assigned, "nurse_id": nurses[0].id}, headers=h)
    client.post("/api/ipd/vitals", json={"patient_id": normal_assigned, "heart_rate": 75}, headers=h)

    abnormal_unassigned = _admit(client, auth_headers, head_nurse, name="Abnormal Unassigned", bed="2")
    client.post("/api/ipd/vitals", json={"patient_id": abnormal_unassigned, "heart_rate": 150}, headers=h)

    overdue_assigned = _admit(client, auth_headers, head_nurse, name="Overdue Assigned", bed="3")
    client.post("/api/ipd/assign", json={"patient_id": overdue_assigned, "nurse_id": nurses[1].id}, headers=h)
    client.post("/api/ipd/tasks", json={"patient_id": overdue_assigned, "description": "Late", "due_date": "2020-01-01T10:00:00"}, headers=h)

    critical_unassigned = _admit(client, auth_headers, head_nurse, name="Critical Unassigned", bed="4")
    client.post("/api/ipd/vitals", json={"patient_id": critical_unassigned, "temperature": 40.0}, headers=h)
    client.post("/api/ipd/tasks", json={"patient_id": critical_unassigned, "description": "Overdue too", "due_date": "2020-01-01T10:00:00"}, headers=h)

    roster = {p["id"]: p for p in client.get("/api/ipd/patients", headers=h).json()}
    assert roster[normal_assigned]["abnormal"] is False
    assert roster[normal_assigned]["overdue_tasks"] == 0
    assert roster[normal_assigned]["assigned_nurse"] is not None

    assert roster[abnormal_unassigned]["abnormal"] is True
    assert roster[abnormal_unassigned]["assigned_nurse"] is None

    assert roster[overdue_assigned]["abnormal"] is False
    assert roster[overdue_assigned]["overdue_tasks"] == 1
    assert roster[overdue_assigned]["assigned_nurse"] is not None

    assert roster[critical_unassigned]["abnormal"] is True
    assert roster[critical_unassigned]["overdue_tasks"] == 1
    assert roster[critical_unassigned]["assigned_nurse"] is None


def test_dashboard_ward_summary_counts_scale_correctly_across_many_patients(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    # 10 normal, 3 abnormal, 2 overdue-only, 5 unassigned (some overlapping categories)
    for i in range(10):
        pid = _admit(client, auth_headers, head_nurse, name=f"Normal {i}", bed=f"n{i}")
        client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[i % 3].id}, headers=h)
    abnormal_ids = []
    for i in range(3):
        pid = _admit(client, auth_headers, head_nurse, name=f"Abnormal {i}", bed=f"a{i}")
        client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 140}, headers=h)
        abnormal_ids.append(pid)
    overdue_ids = []
    for i in range(2):
        pid = _admit(client, auth_headers, head_nurse, name=f"Overdue {i}", bed=f"o{i}")
        client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Late", "due_date": "2020-01-01T10:00:00"}, headers=h)
        overdue_ids.append(pid)
    for i in range(5):
        _admit(client, auth_headers, head_nurse, name=f"Unassigned {i}", bed=f"u{i}")

    roster = client.get("/api/ipd/patients", headers=h).json()
    assert len(roster) == 20
    assert sum(1 for p in roster if p["abnormal"]) == 3
    assert sum(1 for p in roster if p["overdue_tasks"] > 0) == 2
    assert sum(1 for p in roster if p["assigned_nurse"] is None) == 5 + 3 + 2  # unassigned + abnormal + overdue groups, none assigned


def test_nursing_station_sees_same_ward_wide_data_as_headnurse(client, head_nurse, make_user, auth_headers):
    """NursingStation is also a ward-wide viewer (unlike Nurse); confirm parity with HeadNurse
    on the exact same roster data, not just permission to view it."""
    station = make_user(email="station@hn-dashboard.com", role="NursingStation", organization_id=head_nurse.organization_id)
    _admit(client, auth_headers, head_nurse, name="Parity Patient")

    hn_roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    ns_roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert len(hn_roster) == len(ns_roster) == 1
    assert hn_roster[0]["id"] == ns_roster[0]["id"]
    assert hn_roster[0]["abnormal"] == ns_roster[0]["abnormal"]


def test_doctor_sees_same_ward_wide_data_as_headnurse(client, head_nurse, make_user, auth_headers):
    doctor = make_user(email="doc@hn-dashboard.com", role="Doctor", organization_id=head_nurse.organization_id)
    _admit(client, auth_headers, head_nurse, name="Doctor Parity Patient")
    hn_roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    doc_roster = client.get("/api/ipd/patients", headers=auth_headers(doctor)).json()
    assert len(hn_roster) == len(doc_roster) == 1


def test_nurse_sees_strict_subset_of_headnurse_ward_view(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    assigned = _admit(client, auth_headers, head_nurse, name="Assigned To Nurse0", bed="a")
    client.post("/api/ipd/assign", json={"patient_id": assigned, "nurse_id": nurses[0].id}, headers=h)
    _admit(client, auth_headers, head_nurse, name="Not Assigned To Anyone", bed="b")

    hn_roster_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=h).json()}
    nurse_roster_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=auth_headers(nurses[0])).json()}
    assert nurse_roster_ids == {assigned}
    assert nurse_roster_ids.issubset(hn_roster_ids)
    assert len(hn_roster_ids) == 2


def test_dashboard_patient_card_has_latest_vital_summary_fields(client, head_nurse, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse, name="Vital Summary Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "bp_systolic": 118, "bp_diastolic": 76,
                                          "heart_rate": 72, "temperature": 37.1, "oxygen_sat": 97}, headers=h)
    roster = client.get("/api/ipd/patients", headers=h).json()
    lv = roster[0]["latest_vital"]
    assert lv["bp"] == "118/76"
    assert lv["heart_rate"] == 72
    assert lv["temperature"] == 37.1
    assert lv["oxygen_sat"] == 97
    assert lv["recorded_at"] is not None


def test_dashboard_patient_with_no_vitals_has_null_latest_vital(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="No Vitals Patient")
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["latest_vital"] is None
    assert p["abnormal"] is False


def test_dashboard_only_shows_active_patients_not_discharged(client, head_nurse, auth_headers):
    h = auth_headers(head_nurse)
    active_id = _admit(client, auth_headers, head_nurse, name="Still Active", bed="1")
    discharged_id = _admit(client, auth_headers, head_nurse, name="Already Discharged", bed="2")
    client.put(f"/api/patients/{discharged_id}", json={"status": "Discharged"}, headers=h)

    roster_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=h).json()}
    assert active_id in roster_ids
    assert discharged_id not in roster_ids


def test_dashboard_has_nursing_notes_flag_reflects_existence(client, head_nurse, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse, name="Notes Flag Patient")
    roster_before = client.get("/api/ipd/patients", headers=h).json()
    assert roster_before[0]["has_nursing_notes"] is False

    client.post("/api/nursing-notes", json={"patient_id": pid, "subjective": "x", "objective": "", "assessment": "", "plan": ""}, headers=h)
    roster_after = client.get("/api/ipd/patients", headers=h).json()
    assert roster_after[0]["has_nursing_notes"] is True


def test_dashboard_query_count_does_not_scale_with_patient_count(client, head_nurse, nurses, auth_headers, db_session):
    """
    Regression: GET /api/ipd/patients used to run 6 separate queries PER PATIENT (latest
    vital, pending/overdue task counts, active assignment, nurse lookup, has-notes check) --
    verified live during a 200+ case scale-test run, this got slow enough to blow through a
    45-second page-load timeout once the roster grew into the hundreds. A real ward with a
    sizeable active census would hit the same wall. The fix batches every one of those into a
    single query for the whole roster, so the query count must stay roughly constant as the
    patient count grows, not scale linearly with it.
    """
    from sqlalchemy import event
    import app.main as app_main

    h = auth_headers(head_nurse)
    for i in range(15):
        pid = _admit(client, auth_headers, head_nurse, name=f"Patient {i}", bed=str(i))
        client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[i % 3].id}, headers=h)
        client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 80}, headers=h)
        client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Routine check"}, headers=h)

    queries = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(app_main.engine, "before_cursor_execute", _count)
    try:
        resp = client.get("/api/ipd/patients", headers=h)
    finally:
        event.remove(app_main.engine, "before_cursor_execute", _count)

    assert resp.status_code == 200
    assert len(resp.json()) == 15
    # A handful of queries for the whole roster (patients, vitals, tasks, assignments, nurse
    # lookups, notes) -- nowhere near the 15 * 6 = 90+ an N+1 implementation would issue.
    assert len(queries) < 15, f"query count scales with patient count: {len(queries)} queries for 15 patients"
