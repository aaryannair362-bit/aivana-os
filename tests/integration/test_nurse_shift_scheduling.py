"""
GET/PUT /api/ipd/shifts -- the HeadNurse-editable weekly nurse x day shift calendar. Covers the
default-to-"Off" grid, upsert semantics, shift_type/date validation, nurse-must-belong-to-org
enforcement, and role gating.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@shift-sched.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@shift-sched.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def doctor(make_user, head_nurse):
    return make_user(email="doctor@shift-sched.com", role="Doctor", organization_id=head_nurse.organization_id)


@pytest.fixture
def other_org_nurse(make_user):
    return make_user(email="nurse@other-shift-sched.com", role="Nurse")


def test_get_shifts_defaults_every_nurse_to_off(client, head_nurse, nurse, auth_headers):
    resp = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nurses"]) == 1
    assert body["nurses"][0]["nurse_id"] == nurse.id
    assert len(body["nurses"][0]["days"]) == 7
    assert all(d["shift_type"] == "Off" for d in body["nurses"][0]["days"])


def test_get_shifts_week_start_defaults_to_monday_of_current_week(client, head_nurse, auth_headers):
    import datetime
    resp = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse))
    week_start = datetime.date.fromisoformat(resp.json()["week_start"])
    assert week_start.weekday() == 0  # Monday


def test_doctor_and_nurse_cannot_view_shifts(client, doctor, nurse, auth_headers):
    assert client.get("/api/ipd/shifts", headers=auth_headers(doctor)).status_code == 403
    assert client.get("/api/ipd/shifts", headers=auth_headers(nurse)).status_code == 403


def test_set_shift_upserts_and_persists(client, head_nurse, nurse, auth_headers):
    week_start = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse)).json()["week_start"]
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": week_start, "shift_type": "Morning"},
                       headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    body = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse)).json()
    assert body["nurses"][0]["days"][0]["shift_type"] == "Morning"

    # Setting the same (nurse, date) again updates in place rather than duplicating.
    client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": week_start, "shift_type": "Night"},
               headers=auth_headers(head_nurse))
    body2 = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse)).json()
    assert body2["nurses"][0]["days"][0]["shift_type"] == "Night"


@pytest.mark.parametrize("shift_type", ["Morning", "Evening", "Night", "Off"])
def test_all_four_shift_types_accepted(client, head_nurse, nurse, auth_headers, shift_type):
    week_start = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse)).json()["week_start"]
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": week_start, "shift_type": shift_type},
                       headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_invalid_shift_type_rejected(client, head_nurse, nurse, auth_headers):
    week_start = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse)).json()["week_start"]
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": week_start, "shift_type": "Afternoon"},
                       headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_invalid_shift_date_format_rejected(client, head_nurse, nurse, auth_headers):
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": "not-a-date", "shift_type": "Morning"},
                       headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_invalid_week_start_format_rejected(client, head_nurse, auth_headers):
    resp = client.get("/api/ipd/shifts?week_start=not-a-date", headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_cannot_set_shift_for_nurse_in_another_org(client, head_nurse, other_org_nurse, auth_headers):
    week_start = client.get("/api/ipd/shifts", headers=auth_headers(head_nurse)).json()["week_start"]
    resp = client.put("/api/ipd/shifts", json={"nurse_id": other_org_nurse.id, "shift_date": week_start, "shift_type": "Morning"},
                       headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_nurse_and_doctor_cannot_set_shifts(client, nurse, doctor, auth_headers):
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": "2026-01-05", "shift_type": "Morning"},
                       headers=auth_headers(nurse))
    assert resp.status_code == 403
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id, "shift_date": "2026-01-05", "shift_type": "Morning"},
                       headers=auth_headers(doctor))
    assert resp.status_code == 403


def test_missing_required_fields_rejected(client, head_nurse, nurse, auth_headers):
    resp = client.put("/api/ipd/shifts", json={"nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400
