"""
GET /api/ipd/reports and GET /api/ipd/dashboard-summary -- HeadNurse oversight aggregates computed
from real Patient/Task/NurseAssignment rows (task-completion-per-day, patients-by-ward, top raw
diagnosis strings, and the 4 dashboard KPI counts). Covers role gating, correctness, the days-cap,
and that discharged patients don't pollute "Active"-scoped counts.
"""
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@ipd-reports.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@ipd-reports.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def doctor(make_user, head_nurse):
    return make_user(email="doctor@ipd-reports.com", role="Doctor", organization_id=head_nurse.organization_id)


def _admit(client, auth_headers, head_nurse, **overrides):
    payload = {"name": "Report Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    return resp.json()["id"]


def test_doctor_and_nurse_cannot_view_reports_or_dashboard_summary(client, doctor, nurse, auth_headers):
    assert client.get("/api/ipd/reports", headers=auth_headers(doctor)).status_code == 403
    assert client.get("/api/ipd/reports", headers=auth_headers(nurse)).status_code == 403
    assert client.get("/api/ipd/dashboard-summary", headers=auth_headers(doctor)).status_code == 403
    assert client.get("/api/ipd/dashboard-summary", headers=auth_headers(nurse)).status_code == 403


def test_empty_org_reports_and_summary_are_all_zero(client, head_nurse, auth_headers):
    reports = client.get("/api/ipd/reports", headers=auth_headers(head_nurse)).json()
    assert reports["patients_by_ward"] == []
    assert reports["diagnosis_distribution"] == []
    assert all(d["due"] == 0 and d["completed"] == 0 for d in reports["task_completion_per_day"])

    summary = client.get("/api/ipd/dashboard-summary", headers=auth_headers(head_nurse)).json()
    assert summary == {"total_patients": 0, "assigned_patients": 0, "pending_tasks": 0, "completed_tasks": 0}


def test_patients_by_ward_and_diagnosis_distribution(client, head_nurse, auth_headers):
    _admit(client, auth_headers, head_nurse, name="P1", ward="ICU", bed="1", diagnosis="Sepsis")
    _admit(client, auth_headers, head_nurse, name="P2", ward="ICU", bed="2", diagnosis="Sepsis")
    _admit(client, auth_headers, head_nurse, name="P3", ward="General", bed="1", diagnosis="Hypertension")

    reports = client.get("/api/ipd/reports", headers=auth_headers(head_nurse)).json()
    ward_counts = {row["ward"]: row["count"] for row in reports["patients_by_ward"]}
    assert ward_counts == {"ICU": 2, "General": 1}

    diag_counts = {row["diagnosis"]: row["count"] for row in reports["diagnosis_distribution"]}
    assert diag_counts == {"Sepsis": 2, "Hypertension": 1}


def test_discharged_patients_excluded_from_ward_and_diagnosis_breakdown(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Discharged Patient", ward="ICU", diagnosis="Recovered")
    client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    reports = client.get("/api/ipd/reports", headers=auth_headers(head_nurse)).json()
    assert reports["patients_by_ward"] == []
    assert reports["diagnosis_distribution"] == []
    summary = client.get("/api/ipd/dashboard-summary", headers=auth_headers(head_nurse)).json()
    assert summary["total_patients"] == 0


def test_task_completion_counted_on_due_date_within_window(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse)
    today = datetime.utcnow()
    due_today = today.replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
    resp = client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Vitals", "due_date": due_today},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(head_nurse))

    reports = client.get("/api/ipd/reports?days=7", headers=auth_headers(head_nurse)).json()
    today_entry = reports["task_completion_per_day"][-1]
    assert today_entry["due"] == 1
    assert today_entry["completed"] == 1


def test_days_parameter_is_capped_at_90(client, head_nurse, auth_headers):
    resp = client.get("/api/ipd/reports?days=99999", headers=auth_headers(head_nurse))
    assert resp.json()["period_days"] == 90


def test_days_parameter_minimum_is_one(client, head_nurse, auth_headers):
    resp = client.get("/api/ipd/reports?days=0", headers=auth_headers(head_nurse))
    assert resp.json()["period_days"] == 1
    assert len(resp.json()["task_completion_per_day"]) == 1


def test_dashboard_summary_counts_assigned_and_task_states(client, head_nurse, nurse, auth_headers):
    pid1 = _admit(client, auth_headers, head_nurse, name="Assigned Patient", bed="A1")
    pid2 = _admit(client, auth_headers, head_nurse, name="Unassigned Patient", bed="A2")
    client.post("/api/ipd/assign", json={"patient_id": pid1, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))

    t1 = client.post("/api/ipd/tasks", json={"patient_id": pid1, "description": "Task A"}, headers=auth_headers(head_nurse)).json()["id"]
    client.post("/api/ipd/tasks", json={"patient_id": pid2, "description": "Task B"}, headers=auth_headers(head_nurse))
    client.patch(f"/api/ipd/tasks/{t1}", json={"status": "Completed"}, headers=auth_headers(head_nurse))

    summary = client.get("/api/ipd/dashboard-summary", headers=auth_headers(head_nurse)).json()
    assert summary["total_patients"] == 2
    assert summary["assigned_patients"] == 1
    assert summary["pending_tasks"] == 1
    assert summary["completed_tasks"] == 1


def test_reports_and_summary_are_isolated_per_organization(client, head_nurse, make_user, auth_headers):
    other_head_nurse = make_user(email="head@other-ipd-reports.com", role="HeadNurse")
    _admit(client, auth_headers, head_nurse, name="Org A Patient", ward="ICU", diagnosis="Flu")

    other_reports = client.get("/api/ipd/reports", headers=auth_headers(other_head_nurse)).json()
    assert other_reports["patients_by_ward"] == []
    other_summary = client.get("/api/ipd/dashboard-summary", headers=auth_headers(other_head_nurse)).json()
    assert other_summary["total_patients"] == 0
