"""
Task-management scenarios driven by HeadNurse -- task creation is HeadNurse-exclusive, and
HeadNurse can update ANY task regardless of who it's assigned to (regression coverage for the
UI fix: the "Mark Complete" button was previously only shown for the assigned Nurse, never for
HeadNurse, in both places it's rendered in frontend/ipd.html, even though the backend always
allowed it).
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-tasks.com", role="HeadNurse")


@pytest.fixture
def nurse_a(make_user, head_nurse):
    return make_user(email="nurse.a@hn-tasks.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def nurse_b(make_user, head_nurse):
    return make_user(email="nurse.b@hn-tasks.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "HN Task Patient", "ward": "General", "bed": "T1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Task creation
# ---------------------------------------------------------------------------

def test_headnurse_creates_unassigned_task(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Restock IV supplies"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_creates_task_assigned_to_specific_nurse(client, head_nurse, nurse_a, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Administer meds", "nurse_id": nurse_a.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


@pytest.mark.parametrize("description", [
    "Check vitals every 2 hours",
    "Administer 500mg Paracetamol at 14:00",
    "Change dressing on left arm wound",
    "Escort patient to radiology at 10:30",
    "Monitor for allergic reaction post-medication",
    "Collect blood sample for CBC",
    "Assist with ambulation twice daily",
    "Update family on patient condition",
])
def test_headnurse_creates_various_realistic_task_descriptions(client, head_nurse, patient_id, auth_headers, description):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": description}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_creates_many_tasks_for_one_patient(client, head_nurse, patient_id, auth_headers):
    for i in range(10):
        resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": f"Task {i}"}, headers=auth_headers(head_nurse))
        assert resp.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    assert len(tasks) == 10


def test_headnurse_distributes_tasks_across_multiple_nurses_for_one_patient(client, head_nurse, nurse_a, nurse_b, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Task for A", "nurse_id": nurse_a.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Task for B", "nurse_id": nurse_b.id}, headers=auth_headers(head_nurse))
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    nurse_ids = {t["nurse_id"] for t in tasks}
    assert nurse_a.id in nurse_ids
    assert nurse_b.id in nurse_ids


# ---------------------------------------------------------------------------
# HeadNurse can update/complete ANY task -- regression for the fixed UI gap. Verified at the
# API level (the backend was always correct); tests/e2e verifies the UI itself.
# ---------------------------------------------------------------------------

def test_headnurse_completes_a_task_assigned_to_nurse_a(client, head_nurse, nurse_a, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "A's task", "nurse_id": nurse_a.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(head_nurse))
    assert update.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    assert next(t for t in tasks if t["id"] == task_id)["status"] == "Completed"


def test_headnurse_completes_an_unassigned_task(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Nobody's task"}, headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(head_nurse))
    assert update.status_code == 200


def test_headnurse_reassigns_a_tasks_notes_without_touching_status(client, head_nurse, nurse_a, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Needs notes", "nurse_id": nurse_a.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"notes": "Deferred until doctor's round"}, headers=auth_headers(head_nurse))
    assert update.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["notes"] == "Deferred until doctor's round"
    assert task["status"] == "Pending"


def test_headnurse_reopens_a_task_nurse_a_completed(client, head_nurse, nurse_a, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Reopen test", "nurse_id": nurse_a.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(nurse_a))
    reopen = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Pending"}, headers=auth_headers(head_nurse))
    assert reopen.status_code == 200


def test_headnurse_completes_multiple_different_nurses_tasks_in_one_session(client, head_nurse, nurse_a, nurse_b, patient_id, auth_headers):
    t1 = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "A's", "nurse_id": nurse_a.id},
                      headers=auth_headers(head_nurse)).json()["id"]
    t2 = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "B's", "nurse_id": nurse_b.id},
                      headers=auth_headers(head_nurse)).json()["id"]
    assert client.patch(f"/api/ipd/tasks/{t1}", json={"status": "Completed"}, headers=auth_headers(head_nurse)).status_code == 200
    assert client.patch(f"/api/ipd/tasks/{t2}", json={"status": "Completed"}, headers=auth_headers(head_nurse)).status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    assert all(t["status"] == "Completed" for t in tasks)


# ---------------------------------------------------------------------------
# Overdue task tracking as HeadNurse sees it ward-wide
# ---------------------------------------------------------------------------

def test_headnurse_dashboard_surfaces_overdue_tasks_across_multiple_patients(client, head_nurse, auth_headers):
    h = auth_headers(head_nurse)
    pid1 = client.post("/api/ipd/patients", json={"name": "Overdue Patient 1", "ward": "General", "bed": "O1"}, headers=h).json()["id"]
    pid2 = client.post("/api/ipd/patients", json={"name": "Overdue Patient 2", "ward": "General", "bed": "O2"}, headers=h).json()["id"]
    client.post("/api/ipd/tasks", json={"patient_id": pid1, "description": "Overdue 1", "due_date": "2020-01-01T10:00:00"}, headers=h)
    client.post("/api/ipd/tasks", json={"patient_id": pid2, "description": "Overdue 2", "due_date": "2020-01-01T10:00:00"}, headers=h)
    client.post("/api/ipd/tasks", json={"patient_id": pid2, "description": "Future", "due_date": "2099-01-01T10:00:00"}, headers=h)

    roster = {p["id"]: p for p in client.get("/api/ipd/patients", headers=h).json()}
    assert roster[pid1]["overdue_tasks"] == 1
    assert roster[pid2]["overdue_tasks"] == 1


def test_headnurse_completing_overdue_task_removes_it_from_overdue_count(client, head_nurse, auth_headers):
    h = auth_headers(head_nurse)
    pid = client.post("/api/ipd/patients", json={"name": "Fix Overdue Patient", "ward": "General", "bed": "F1"}, headers=h).json()["id"]
    task_id = client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Late task", "due_date": "2020-01-01T10:00:00"},
                           headers=h).json()["id"]
    roster = {p["id"]: p for p in client.get("/api/ipd/patients", headers=h).json()}
    assert roster[pid]["overdue_tasks"] == 1

    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=h)
    roster = {p["id"]: p for p in client.get("/api/ipd/patients", headers=h).json()}
    assert roster[pid]["overdue_tasks"] == 0


# ---------------------------------------------------------------------------
# Task validation edge cases specifically exercised by HeadNurse (the actor with the widest
# task-management permissions)
# ---------------------------------------------------------------------------

def test_headnurse_create_task_missing_patient_id_rejected(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"description": "no patient"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_headnurse_create_task_missing_description_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_headnurse_create_task_empty_description_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": ""}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_headnurse_update_nonexistent_task_returns_404(client, head_nurse, auth_headers):
    resp = client.patch("/api/ipd/tasks/999999", json={"status": "Completed"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_headnurse_cannot_create_task_for_other_orgs_patient(client, head_nurse, make_user, db_session, auth_headers):
    from app.models import Patient
    other_head = make_user(email="other-head@hn-tasks.com", role="HeadNurse")
    patient = Patient(name="Foreign Patient", ward="General", bed="F1",
                       organization_id=other_head.organization_id, created_by=other_head.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient.id, "description": "cross org"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404
