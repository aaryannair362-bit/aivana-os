"""
Complete end-to-end coverage of the NursingStation role (the ward/front-desk login): login,
session, and a realistic front-desk day. NursingStation is a deliberately narrow role compared
to HeadNurse/Nurse -- it admits patients and manages administrative patient info (ward, bed,
diagnosis, status/discharge), and can read the ward roster/patient chart/vitals/tasks, but
cannot record any clinical data itself (no vitals, no tasks, no nursing notes, no voice
features) and cannot manage nurse assignments. Confirmed against backend/app/main.py: exactly
six endpoints check `is_nursing_station()` -- create_ipd_patient, update_patient,
get_ipd_patients, get_patient_details, get_vitals, get_tasks.
"""
import pytest


@pytest.fixture
def station(make_user):
    return make_user(email="station@ns-workflow.com", role="NursingStation")


@pytest.fixture
def head_nurse(make_user, station):
    return make_user(email="head@ns-workflow.com", role="HeadNurse", organization_id=station.organization_id)


@pytest.fixture
def nurse(make_user, station):
    return make_user(email="nurse@ns-workflow.com", role="Nurse", organization_id=station.organization_id)


# ---------------------------------------------------------------------------
# Login / session
# ---------------------------------------------------------------------------

def test_station_login_succeeds_and_returns_role(client, station):
    resp = client.post("/api/auth/login", json={"email": station.email, "password": "Str0ng!Passw0rd#1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] == "NursingStation"
    assert "access_token" in data


def test_station_wrong_password_rejected(client, station):
    resp = client.post("/api/auth/login", json={"email": station.email, "password": "WrongPassword123!"})
    assert resp.status_code == 401


def test_station_me_endpoint_reflects_role(client, station, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers(station))
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "NursingStation"


def test_station_token_refresh_preserves_role(client, station):
    login = client.post("/api/auth/login", json={"email": station.email, "password": "Str0ng!Passw0rd#1"}).json()
    refresh = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refresh.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh.json()['access_token']}"})
    assert me.json()["user"]["role"] == "NursingStation"


def test_station_locked_out_after_five_failed_attempts(client, station):
    for _ in range(5):
        client.post("/api/auth/login", json={"email": station.email, "password": "wrong"})
    resp = client.post("/api/auth/login", json={"email": station.email, "password": "Str0ng!Passw0rd#1"})
    assert resp.status_code == 403
    assert "locked" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Full realistic front-desk day: admit several patients, update their administrative details,
# read the chart to answer a family's question, discharge one at end of shift.
# ---------------------------------------------------------------------------

def test_full_station_day_end_to_end(client, station, head_nurse, nurse, auth_headers):
    s = auth_headers(station)

    # 1. Roster starts empty.
    assert client.get("/api/ipd/patients", headers=s).json() == []

    # 2. Admit a walk-in patient.
    admit = client.post("/api/ipd/patients", json={"name": "Front Desk Patient", "age": 34, "gender": "Female",
                                                     "ward": "General", "bed": "F1", "diagnosis": "Pending assessment"},
                         headers=s)
    assert admit.status_code == 200
    pid = admit.json()["id"]

    # 3. Update administrative details once a bed/ward is confirmed.
    update = client.put(f"/api/patients/{pid}", json={"ward": "Maternity", "bed": "M4"}, headers=s)
    assert update.status_code == 200

    # 4. HeadNurse assigns a nurse (station cannot do this itself).
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))

    # 5. Nurse records vitals during the day (station cannot).
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 76}, headers=auth_headers(nurse))

    # 6. Station reads the full chart to answer a query at the desk.
    details = client.get(f"/api/patients/{pid}/details", headers=s).json()
    assert details["patient"]["ward"] == "Maternity"
    assert len(details["vitals"]) == 1
    assert details["patient"]["assigned_nurse"]["id"] == nurse.id

    # 7. Station reads the ward-wide roster.
    roster = client.get("/api/ipd/patients", headers=s).json()
    assert len(roster) == 1
    assert roster[0]["assigned_nurse"]["id"] == nurse.id

    # 8. End of stay: station processes the discharge.
    discharge = client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=s)
    assert discharge.status_code == 200
    assert client.get("/api/ipd/patients", headers=s).json() == []

    # 9. Discharged patient's chart remains reviewable at the desk.
    final_details = client.get(f"/api/patients/{pid}/details", headers=s).json()
    assert final_details["patient"]["status"] == "Discharged"


def test_station_admits_and_manages_multiple_patients_in_parallel(client, station, auth_headers):
    s = auth_headers(station)
    ids = []
    for i in range(8):
        resp = client.post("/api/ipd/patients", json={"name": f"Parallel Patient {i}", "ward": "General", "bed": str(i)}, headers=s)
        ids.append(resp.json()["id"])
    for pid in ids[:4]:
        client.put(f"/api/patients/{pid}", json={"diagnosis": "Updated on arrival"}, headers=s)
    roster = client.get("/api/ipd/patients", headers=s).json()
    assert len(roster) == 8
    updated = [p for p in roster if p["diagnosis"] == "Updated on arrival"]
    assert len(updated) == 4


# ---------------------------------------------------------------------------
# Cross-organization isolation as the NursingStation actor, across every endpoint it can call.
# ---------------------------------------------------------------------------

@pytest.fixture
def other_org_patient(make_user, db_session):
    from app.models import Patient
    other_station = make_user(email="other-station@ns-workflow.com", role="NursingStation")
    patient = Patient(name="Other Org Patient", ward="General", bed="O1",
                       organization_id=other_station.organization_id, created_by=other_station.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient


@pytest.mark.parametrize("method,path_fn,body", [
    ("GET", lambda pid: f"/api/patients/{pid}/details", None),
    ("PUT", lambda pid: f"/api/patients/{pid}", {"diagnosis": "tampered"}),
    ("GET", lambda pid: f"/api/ipd/vitals/{pid}", None),
    ("GET", lambda pid: f"/api/ipd/tasks/{pid}", None),
])
def test_station_blocked_from_other_orgs_patient_on_every_readable_endpoint(client, station, other_org_patient, auth_headers, method, path_fn, body):
    path = path_fn(other_org_patient.id)
    s = auth_headers(station)
    resp = client.get(path, headers=s) if method == "GET" else client.put(path, json=body, headers=s)
    assert resp.status_code in (403, 404), f"{method} {path}: cross-org access should be blocked, got {resp.status_code}"


def test_station_from_org_a_does_not_see_org_bs_patients_in_roster(client, station, other_org_patient, auth_headers):
    roster_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=auth_headers(station)).json()}
    assert other_org_patient.id not in roster_ids
