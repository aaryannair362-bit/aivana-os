"""
Realistic busy-front-desk scenarios for NursingStation: multiple station operators working the
same desk concurrently, admission input edge cases (the data a real intake form captures),
and the front desk's role in coordinating with HeadNurse/Nurse across a full ward day.
"""
import pytest


@pytest.fixture
def station(make_user):
    return make_user(email="station@ns-realistic.com", role="NursingStation")


@pytest.fixture
def station_2(make_user, station):
    """A second front-desk operator on the same shift, same organization -- realistic for a
    busy multi-specialty hospital with more than one admission desk."""
    return make_user(email="station2@ns-realistic.com", role="NursingStation", organization_id=station.organization_id)


@pytest.fixture
def head_nurse(make_user, station):
    return make_user(email="head@ns-realistic.com", role="HeadNurse", organization_id=station.organization_id)


def _admit(client, auth_headers, actor, **overrides):
    payload = {"name": "Realistic Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(actor))
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Multiple station operators sharing the same desk/organization
# ---------------------------------------------------------------------------

def test_two_station_operators_see_the_same_shared_roster(client, station, station_2, auth_headers):
    _admit(client, auth_headers, station, name="Admitted By Operator One")
    roster_1 = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    roster_2 = client.get("/api/ipd/patients", headers=auth_headers(station_2)).json()
    assert len(roster_1) == len(roster_2) == 1
    assert roster_1[0]["id"] == roster_2[0]["id"]


def test_second_operator_can_edit_a_patient_the_first_admitted(client, station, station_2, auth_headers):
    pid = _admit(client, auth_headers, station, name="Handoff Patient")
    resp = client.put(f"/api/patients/{pid}", json={"diagnosis": "Updated by second operator"}, headers=auth_headers(station_2))
    assert resp.status_code == 200
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["diagnosis"] == "Updated by second operator"


def test_second_operator_can_discharge_a_patient_the_first_admitted(client, station, station_2, auth_headers):
    pid = _admit(client, auth_headers, station, name="Cross-Operator Discharge")
    resp = client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=auth_headers(station_2))
    assert resp.status_code == 200


def test_both_operators_admitting_simultaneously_produce_distinct_patients(client, station, station_2, auth_headers):
    id1 = _admit(client, auth_headers, station, name="Simultaneous A", bed="A")
    id2 = _admit(client, auth_headers, station_2, name="Simultaneous B", bed="B")
    assert id1 != id2
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert len(roster) == 2


# ---------------------------------------------------------------------------
# Realistic intake-form input variety
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Mary O'Brien",
    "Jean-Pierre Dubois",
    "Dr. Smith Jr.",
    "María José García",
    "Muhammad ibn Abdullah",
    "李明",
    "田中太郎",
])
def test_station_admits_patients_with_realistic_international_names(client, station, auth_headers, name):
    pid = _admit(client, auth_headers, station, name=name)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["name"] == name


def test_station_admits_patient_with_emergency_walk_in_minimal_info(client, station, auth_headers):
    """Emergency intake often has name and ward only, everything else filled in later."""
    resp = client.post("/api/ipd/patients", json={"name": "Unknown Male, approx 40s", "ward": "Emergency"},
                        headers=auth_headers(station))
    pid = resp.json()["id"]
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["diagnosis"] is None
    assert details["patient"]["bed"] is None


def test_station_updates_walk_in_patient_once_identity_confirmed(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="Unknown Male, approx 40s", ward="Emergency")
    resp = client.put(f"/api/patients/{pid}", json={"diagnosis": "Identity confirmed: John Smith, DOB verified"},
                       headers=auth_headers(station))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Full-day coordination between the front desk and clinical staff
# ---------------------------------------------------------------------------

def test_station_admits_headnurse_assigns_and_manages_clinically_station_handles_paperwork(
    client, station, head_nurse, make_user, auth_headers
):
    """A realistic division of labor across a shift: station admits and does paperwork/
    discharge, head nurse handles all clinical assignment/oversight."""
    nurse = make_user(email="nurse@ns-realistic.com", role="Nurse", organization_id=station.organization_id)
    s = auth_headers(station)
    hn = auth_headers(head_nurse)

    pid = _admit(client, auth_headers, station, name="Coordination Patient")
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=hn)
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 78}, headers=auth_headers(nurse))
    client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Discharge paperwork prep"}, headers=hn)

    # Station reviews readiness for discharge via the chart.
    details = client.get(f"/api/patients/{pid}/details", headers=s).json()
    assert len(details["vitals"]) == 1
    assert len(details["tasks"]) == 1

    discharge = client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=s)
    assert discharge.status_code == 200


def test_station_processes_a_full_days_admissions_and_discharges(client, station, auth_headers):
    """A representative busy day: 15 admissions, 6 discharges by end of shift."""
    s = auth_headers(station)
    ids = [_admit(client, auth_headers, station, name=f"Day Patient {i}", bed=str(i)) for i in range(15)]
    for pid in ids[:6]:
        client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=s)
    roster = client.get("/api/ipd/patients", headers=s).json()
    assert len(roster) == 9


def test_station_handles_readmission_of_a_previously_discharged_patient(client, station, auth_headers):
    """A patient bounces back (common scenario) -- station admits a fresh Patient record
    rather than reactivating the old one (no re-admission linkage exists in this system)."""
    s = auth_headers(station)
    old_pid = _admit(client, auth_headers, station, name="Bounce Back Patient", bed="1")
    client.put(f"/api/patients/{old_pid}", json={"status": "Discharged"}, headers=s)
    new_pid = _admit(client, auth_headers, station, name="Bounce Back Patient", bed="2")
    assert new_pid != old_pid
    roster_ids = {p["id"] for p in client.get("/api/ipd/patients", headers=s).json()}
    assert new_pid in roster_ids
    assert old_pid not in roster_ids


# ---------------------------------------------------------------------------
# Station's admission immediately usable by clinical roles without any extra step
# ---------------------------------------------------------------------------

def test_freshly_admitted_patient_has_zero_pending_and_zero_overdue_tasks(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="Zero State Patient")
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["pending_tasks"] == 0
    assert p["overdue_tasks"] == 0
    assert p["abnormal"] is False
    assert p["has_nursing_notes"] is False


def test_freshly_admitted_patient_visible_in_nurse_workload_relevant_roster_immediately(client, station, head_nurse, make_user, auth_headers):
    nurse = make_user(email="nurse2@ns-realistic.com", role="Nurse", organization_id=station.organization_id)
    pid = _admit(client, auth_headers, station, name="Immediately Assignable")
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    workload = {w["id"]: w["patient_count"] for w in client.get("/api/ipd/nurse-workload", headers=auth_headers(head_nurse)).json()}
    assert workload[nurse.id] == 1
