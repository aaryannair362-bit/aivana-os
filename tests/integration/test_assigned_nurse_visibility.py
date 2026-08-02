"""
Tests for the assigned_nurse visibility feature.

Before this feature, GET /api/ipd/patients and GET /api/patients/{id}/details told the caller
nothing about which nurse (if any) currently held the active assignment for a patient -- a
head nurse assigning nurses for the day had no way to see the current roster state at a glance
without cross-referencing a separate system. Both endpoints now include an assigned_nurse
{id, email} object (or null when nobody is currently assigned), and vitals/tasks/nursing_notes
items in patient details include the recording/assigned nurse's email alongside the raw id.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@nurse-visibility.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@nurse-visibility.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Visibility Patient", "ward": "General", "bed": "N1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


def test_unassigned_patient_shows_null_assigned_nurse_in_list(client, head_nurse, patient_id, auth_headers):
    patients = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in patients if p["id"] == patient_id)
    assert p["assigned_nurse"] is None


def test_assigned_patient_shows_nurse_email_in_list(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    patients = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in patients if p["id"] == patient_id)
    assert p["assigned_nurse"] == {"id": nurse.id, "email": nurse.email}


def test_reassignment_updates_assigned_nurse_in_list(client, head_nurse, nurse, make_user, patient_id, auth_headers):
    nurse_2 = make_user(email="nurse2@nurse-visibility.com", role="Nurse", organization_id=head_nurse.organization_id)
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse_2.id}, headers=auth_headers(head_nurse))
    patients = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in patients if p["id"] == patient_id)
    assert p["assigned_nurse"]["id"] == nurse_2.id


def test_unassigned_patient_shows_null_assigned_nurse_in_details(client, head_nurse, patient_id, auth_headers):
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["patient"]["assigned_nurse"] is None


def test_assigned_patient_shows_nurse_email_in_details(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["patient"]["assigned_nurse"] == {"id": nurse.id, "email": nurse.email}


def test_vitals_include_recording_nurse_email(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 80}, headers=auth_headers(nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["vitals"][0]["nurse_email"] == nurse.email
    assert details["vitals"][0]["nurse_id"] == nurse.id


def test_tasks_include_assigned_nurse_email(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Check IV", "nurse_id": nurse.id},
                headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["tasks"][0]["nurse_email"] == nurse.email


def test_unassigned_task_has_null_nurse_email(client, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Restock"}, headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["tasks"][0]["nurse_email"] is None


def test_nursing_notes_include_authoring_nurse_email(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "Fine", "objective": "", "assessment": "", "plan": ""},
                headers=auth_headers(nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["nursing_notes"][0]["nurse_email"] == nurse.email


def test_nurse_role_sees_own_email_as_assigned_nurse(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    patients = client.get("/api/ipd/patients", headers=auth_headers(nurse)).json()
    p = next(p for p in patients if p["id"] == patient_id)
    assert p["assigned_nurse"]["email"] == nurse.email


# ---------------------------------------------------------------------------
# Overdue-task convenience feature
# ---------------------------------------------------------------------------

def test_task_with_future_due_date_not_overdue(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Future task",
                                                 "due_date": "2099-01-01T10:00:00"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["is_overdue"] is False


def test_task_with_past_due_date_is_overdue(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Past task",
                                                 "due_date": "2020-01-01T10:00:00"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["is_overdue"] is True


def test_completed_task_with_past_due_date_is_not_overdue(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Late but done",
                                                 "due_date": "2020-01-01T10:00:00", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(nurse))
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["is_overdue"] is False


def test_task_with_no_due_date_is_not_overdue(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "No deadline"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["is_overdue"] is False


def test_ward_roster_overdue_tasks_count(client, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Overdue 1", "due_date": "2020-01-01T10:00:00"},
                headers=auth_headers(head_nurse))
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Overdue 2", "due_date": "2020-01-02T10:00:00"},
                headers=auth_headers(head_nurse))
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Future", "due_date": "2099-01-01T10:00:00"},
                headers=auth_headers(head_nurse))
    patients = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in patients if p["id"] == patient_id)
    assert p["overdue_tasks"] == 2
    assert p["pending_tasks"] == 3


def test_patient_details_tasks_include_is_overdue(client, head_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Overdue", "due_date": "2020-01-01T10:00:00"},
                headers=auth_headers(head_nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["tasks"][0]["is_overdue"] is True
