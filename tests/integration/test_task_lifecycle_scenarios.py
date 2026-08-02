"""
Task lifecycle scenarios: creation, updates, completion, reopening, and the authorization
boundary between "the assigned nurse for this task" and "any nurse on the ward".
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@task-lifecycle.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@task-lifecycle.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def other_nurse(make_user, head_nurse):
    return make_user(email="other-nurse@task-lifecycle.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Task Lifecycle Patient", "ward": "General", "bed": "T1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


def test_task_created_with_default_status_pending(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Take blood sample"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "Pending"


def test_assigned_nurse_can_mark_own_task_completed(client, head_nurse, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Give medication", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(nurse))
    assert update.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "Completed"
    assert task["completed_at"] is not None


def test_completing_a_task_sets_completed_at_timestamp(client, head_nurse, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Wound check", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    tasks_before = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    assert next(t for t in tasks_before if t["id"] == task_id)["completed_at"] is None
    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(nurse))
    tasks_after = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    assert next(t for t in tasks_after if t["id"] == task_id)["completed_at"] is not None


def test_nurse_cannot_complete_another_nurses_task(client, head_nurse, nurse, other_nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "IV check", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(other_nurse))
    assert update.status_code == 403


def test_head_nurse_can_update_any_nurses_task(client, head_nurse, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Dressing change", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(head_nurse))
    assert update.status_code == 200


def test_nursing_station_cannot_update_tasks(client, head_nurse, make_user, patient_id, auth_headers):
    station = make_user(email="station@task-lifecycle.com", role="NursingStation", organization_id=head_nurse.organization_id)
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Vitals check"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "InProgress"}, headers=auth_headers(station))
    assert update.status_code == 403


def test_doctor_cannot_update_tasks(client, head_nurse, make_user, patient_id, auth_headers):
    doctor = make_user(email="doctor@task-lifecycle.com", role="Doctor", organization_id=head_nurse.organization_id)
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Vitals check"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "InProgress"}, headers=auth_headers(doctor))
    assert update.status_code == 403


def test_reopening_a_completed_task(client, head_nurse, nurse, patient_id, auth_headers):
    """A task marked Completed by mistake can be reopened by setting status back to Pending."""
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Reopen test", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(nurse))
    reopen = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Pending"}, headers=auth_headers(nurse))
    assert reopen.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "Pending"
    # completed_at is not cleared on reopen -- documents current behavior (no explicit reset).
    assert task["completed_at"] is not None


def test_updating_task_notes_without_changing_status(client, head_nurse, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Notes test", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"notes": "Patient was asleep, will retry in 30 min"},
                           headers=auth_headers(nurse))
    assert update.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "Pending"
    assert task["notes"] == "Patient was asleep, will retry in 30 min"


def test_update_task_arbitrary_status_string_accepted_without_validation(client, head_nurse, patient_id, auth_headers):
    """Documents current behavior: status is a free-text column with no enum/CHECK constraint,
    so any string is accepted -- not just Pending/InProgress/Completed."""
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Weird status test"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    update = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "OnHold-AwaitingLabResults"},
                           headers=auth_headers(head_nurse))
    assert update.status_code == 200
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(head_nurse)).json()
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "OnHold-AwaitingLabResults"


def test_update_nonexistent_task_returns_404(client, head_nurse, auth_headers):
    resp = client.patch("/api/ipd/tasks/999999", json={"status": "Completed"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_multiple_tasks_per_patient_tracked_independently(client, head_nurse, nurse, patient_id, auth_headers):
    descriptions = ["Give medication", "Check vitals", "Change dressing", "Update family"]
    task_ids = []
    for desc in descriptions:
        resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": desc, "nurse_id": nurse.id},
                            headers=auth_headers(head_nurse))
        task_ids.append(resp.json()["id"])
    client.patch(f"/api/ipd/tasks/{task_ids[0]}", json={"status": "Completed"}, headers=auth_headers(nurse))
    client.patch(f"/api/ipd/tasks/{task_ids[1]}", json={"status": "Completed"}, headers=auth_headers(nurse))

    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    assert len(tasks) == 4
    completed = [t for t in tasks if t["status"] == "Completed"]
    pending = [t for t in tasks if t["status"] == "Pending"]
    assert len(completed) == 2
    assert len(pending) == 2

    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in roster if p["id"] == patient_id)
    assert p["pending_tasks"] == 2


def test_task_due_date_accepts_various_iso_formats(client, head_nurse, patient_id, auth_headers):
    for due in ["2026-08-01T10:00:00", "2026-08-01T10:00:00Z", "2026-08-01T10:00:00+05:30", "2026-08-01"]:
        resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": f"Due format {due}", "due_date": due},
                            headers=auth_headers(head_nurse))
        assert resp.status_code == 200, f"due_date={due!r} unexpectedly rejected: {resp.text}"


def test_task_without_due_date_accepted(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "No due date"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_unassigned_nurse_cannot_view_tasks_for_patient(client, head_nurse, other_nurse, patient_id, auth_headers):
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Private task"},
                headers=auth_headers(head_nurse))
    resp = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(other_nurse))
    assert resp.status_code == 403
