"""
Regression tests for POST /api/ipd/tasks's nurse_id validation fix.

Before this fix, create_task stored data.get("nurse_id") verbatim with no existence, role, or
organization check at all -- unlike its sibling POST /api/ipd/assign, which does validate all
three. A head nurse could accidentally (typo'd id, stale dropdown, copy-paste error) create a
task pointing at a nonexistent user, a Doctor's user id, or a nurse belonging to a different
organization, silently producing a task nobody could ever see or complete. nurse_id is now
validated the same way assign_patient already validates it.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@task-nurse-id.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@task-nurse-id.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def doctor(make_user, head_nurse):
    return make_user(email="doctor@task-nurse-id.com", role="Doctor", organization_id=head_nurse.organization_id)


@pytest.fixture
def other_org_nurse(make_user):
    return make_user(email="nurse@other-task-org.com", role="Nurse")


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Task Nurse Validation Patient", "ward": "General", "bed": "T1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


def test_create_task_with_valid_nurse_id_succeeds(client, head_nurse, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Give medication", "nurse_id": nurse.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_create_task_with_no_nurse_id_is_unassigned_and_succeeds(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Restock supplies"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_create_task_with_nonexistent_nurse_id_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Give medication", "nurse_id": 999999},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_create_task_with_doctors_id_as_nurse_id_rejected(client, head_nurse, doctor, patient_id, auth_headers):
    """nurse_id must reference a User with role Nurse specifically -- a Doctor's id (a real,
    existing user in the same org) must not silently be accepted as a nurse assignment."""
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Give medication", "nurse_id": doctor.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_create_task_with_head_nurses_own_id_as_nurse_id_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Give medication", "nurse_id": head_nurse.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_create_task_with_cross_org_nurse_id_rejected(client, head_nurse, other_org_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Give medication", "nurse_id": other_org_nurse.id},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_create_task_with_null_nurse_id_is_unassigned_and_succeeds(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Check chart", "nurse_id": None},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_task_created_with_valid_nurse_is_visible_to_that_nurse(client, head_nurse, nurse, patient_id, auth_headers):
    create_resp = client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Administer IV", "nurse_id": nurse.id},
                               headers=auth_headers(head_nurse))
    task_id = create_resp.json()["id"]
    # The nurse must be assigned to the patient to view tasks for it at all.
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    tasks = client.get(f"/api/ipd/tasks/{patient_id}", headers=auth_headers(nurse)).json()
    assert any(t["id"] == task_id for t in tasks)


def test_reject_before_creating_partial_task_row(client, head_nurse, patient_id, auth_headers, db_session):
    """A rejected nurse_id must not leave a Task row behind at all (no partial writes)."""
    from app.models import Task
    client.post("/api/ipd/tasks", json={"patient_id": patient_id, "description": "Should not be created", "nurse_id": 999999},
                headers=auth_headers(head_nurse))
    assert db_session.query(Task).filter(Task.patient_id == patient_id).count() == 0
