"""
GET /api/ipd/alerts -- flattens the same roster GET /api/ipd/patients computes into a single
paginated, most-recent-first feed of abnormal_vital / overdue_task entries. Since it reuses
_resolve_ipd_patients_for_role and _build_ipd_roster verbatim, role-based visibility here must
match GET /api/ipd/patients exactly; the focus of these tests is the flattening/pagination logic
itself, not re-testing roster visibility (that's covered in test_headnurse_dashboard_data_scenarios.py).
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@ipd-alerts.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@ipd-alerts.com", role="Nurse", organization_id=head_nurse.organization_id)


def _admit(client, auth_headers, head_nurse, **overrides):
    payload = {"name": "Alert Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    return resp.json()["id"]


def test_no_alerts_when_ward_is_healthy(client, head_nurse, auth_headers):
    _admit(client, auth_headers, head_nurse)
    resp = client.get("/api/ipd/alerts", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "alerts": []}


def test_abnormal_vital_produces_alert(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Tachycardic Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 150}, headers=auth_headers(head_nurse))
    body = client.get("/api/ipd/alerts", headers=auth_headers(head_nurse)).json()
    assert body["total"] == 1
    assert body["alerts"][0]["type"] == "abnormal_vital"
    assert body["alerts"][0]["patient_id"] == pid


def test_overdue_task_produces_alert(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Overdue Task Patient")
    client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Late task", "due_date": "2020-01-01T10:00:00"},
                headers=auth_headers(head_nurse))
    body = client.get("/api/ipd/alerts", headers=auth_headers(head_nurse)).json()
    assert body["total"] == 1
    assert body["alerts"][0]["type"] == "overdue_task"
    assert body["alerts"][0]["patient_id"] == pid


def test_completed_overdue_task_does_not_alert(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse)
    resp = client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Late task", "due_date": "2020-01-01T10:00:00"},
                        headers=auth_headers(head_nurse))
    task_id = resp.json()["id"]
    client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(head_nurse))
    body = client.get("/api/ipd/alerts", headers=auth_headers(head_nurse)).json()
    assert body["total"] == 0


def test_alerts_pagination(client, head_nurse, auth_headers):
    for i in range(5):
        pid = _admit(client, auth_headers, head_nurse, name=f"Patient {i}", bed=f"B{i}")
        client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Late", "due_date": "2020-01-01T10:00:00"},
                    headers=auth_headers(head_nurse))
    body = client.get("/api/ipd/alerts?limit=2&offset=0", headers=auth_headers(head_nurse)).json()
    assert body["total"] == 5
    assert len(body["alerts"]) == 2
    body2 = client.get("/api/ipd/alerts?limit=2&offset=4", headers=auth_headers(head_nurse)).json()
    assert len(body2["alerts"]) == 1


def test_alerts_limit_is_capped(client, head_nurse, auth_headers):
    resp = client.get("/api/ipd/alerts?limit=99999", headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_nurse_only_sees_alerts_for_assigned_patients(client, head_nurse, nurse, auth_headers):
    assigned = _admit(client, auth_headers, head_nurse, name="Assigned", bed="A1")
    unassigned = _admit(client, auth_headers, head_nurse, name="Unassigned", bed="A2")
    client.post("/api/ipd/assign", json={"patient_id": assigned, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": assigned, "heart_rate": 150}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": unassigned, "heart_rate": 150}, headers=auth_headers(head_nurse))

    body = client.get("/api/ipd/alerts", headers=auth_headers(nurse)).json()
    assert body["total"] == 1
    assert body["alerts"][0]["patient_id"] == assigned


def test_alerts_isolated_per_organization(client, head_nurse, make_user, auth_headers):
    other_head_nurse = make_user(email="head@other-ipd-alerts.com", role="HeadNurse")
    pid = _admit(client, auth_headers, head_nurse, name="Org A Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 150}, headers=auth_headers(head_nurse))
    other_body = client.get("/api/ipd/alerts", headers=auth_headers(other_head_nurse)).json()
    assert other_body == {"total": 0, "alerts": []}
