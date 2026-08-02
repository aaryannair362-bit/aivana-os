"""
Admission and assignment scenarios driven specifically by HeadNurse -- the assignment half is
entirely HeadNurse-exclusive (POST /api/ipd/assign, /unassign, /nurse-workload), so this is the
primary place that functionality gets end-to-end coverage.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-admit-assign.com", role="HeadNurse")


@pytest.fixture
def nurses(make_user, head_nurse):
    return [make_user(email=f"nurse{i}@hn-admit-assign.com", role="Nurse", organization_id=head_nurse.organization_id)
            for i in range(4)]


def _admit(client, auth_headers, head_nurse, **overrides):
    payload = {"name": "HN Admit Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Admission as HeadNurse (regression coverage for the fixed admit-button UI bug -- these
# confirm the backend side, which was always correct; tests/e2e covers the UI fix itself)
# ---------------------------------------------------------------------------

def test_headnurse_can_admit_a_patient(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Direct HN Admit")
    assert pid is not None
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(head_nurse)).json()
    assert details["patient"]["name"] == "Direct HN Admit"


@pytest.mark.parametrize("ward", ["ICU", "General", "Maternity", "Pediatrics", "Emergency", "Post-Op", "Isolation"])
def test_headnurse_admits_patients_into_every_ward_type(client, head_nurse, auth_headers, ward):
    pid = _admit(client, auth_headers, head_nurse, ward=ward)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(head_nurse)).json()
    assert details["patient"]["ward"] == ward


def test_newly_admitted_patient_by_headnurse_is_immediately_assignable(client, head_nurse, nurses, auth_headers):
    pid = _admit(client, auth_headers, head_nurse)
    resp = client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Assignment lifecycle: initial assign, reassign (shift handoff), unassign, reassign again
# ---------------------------------------------------------------------------

def test_assign_then_reassign_then_unassign_then_reassign_cycle(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse)

    r1 = client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=h)
    assert r1.status_code == 200
    roster = client.get("/api/ipd/patients", headers=h).json()
    assert roster[0]["assigned_nurse"]["id"] == nurses[0].id

    r2 = client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[1].id}, headers=h)
    assert r2.status_code == 200
    roster = client.get("/api/ipd/patients", headers=h).json()
    assert roster[0]["assigned_nurse"]["id"] == nurses[1].id

    r3 = client.post("/api/ipd/unassign", json={"patient_id": pid}, headers=h)
    assert r3.status_code == 200
    roster = client.get("/api/ipd/patients", headers=h).json()
    assert roster[0]["assigned_nurse"] is None

    r4 = client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[2].id}, headers=h)
    assert r4.status_code == 200
    roster = client.get("/api/ipd/patients", headers=h).json()
    assert roster[0]["assigned_nurse"]["id"] == nurses[2].id


def test_unassign_on_already_unassigned_patient_is_a_safe_no_op(client, head_nurse, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse)
    resp = client.post("/api/ipd/unassign", json={"patient_id": pid}, headers=h)
    assert resp.status_code == 200
    assert "no active assignment" in resp.json()["message"].lower()


def test_unassign_requires_patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/unassign", json={}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_unassign_nonexistent_patient_returns_404(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/unassign", json={"patient_id": 999999}, headers=auth_headers(head_nurse))
    assert resp.status_code == 404


@pytest.mark.parametrize("role", ["Nurse", "NursingStation", "Doctor", "Admin"])
def test_only_headnurse_can_unassign(client, head_nurse, make_user, auth_headers, role):
    other = make_user(email=f"{role.lower()}@hn-admit-assign.com", role=role, organization_id=head_nurse.organization_id)
    pid = _admit(client, auth_headers, head_nurse)
    resp = client.post("/api/ipd/unassign", json={"patient_id": pid}, headers=auth_headers(other))
    assert resp.status_code == 403


def test_unassign_does_not_affect_other_patients_assignments(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    pid1 = _admit(client, auth_headers, head_nurse, name="Keep Assigned", bed="K1")
    pid2 = _admit(client, auth_headers, head_nurse, name="Get Unassigned", bed="U1")
    client.post("/api/ipd/assign", json={"patient_id": pid1, "nurse_id": nurses[0].id}, headers=h)
    client.post("/api/ipd/assign", json={"patient_id": pid2, "nurse_id": nurses[0].id}, headers=h)

    client.post("/api/ipd/unassign", json={"patient_id": pid2}, headers=h)

    roster = {p["id"]: p for p in client.get("/api/ipd/patients", headers=h).json()}
    assert roster[pid1]["assigned_nurse"] is not None
    assert roster[pid2]["assigned_nurse"] is None


def test_unassigning_closes_the_nurses_visibility_immediately(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse)
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=h)
    assert len(client.get("/api/ipd/patients", headers=auth_headers(nurses[0])).json()) == 1
    client.post("/api/ipd/unassign", json={"patient_id": pid}, headers=h)
    assert client.get("/api/ipd/patients", headers=auth_headers(nurses[0])).json() == []


# ---------------------------------------------------------------------------
# Nurse workload endpoint (new HeadNurse convenience feature)
# ---------------------------------------------------------------------------

def test_nurse_workload_shows_zero_for_all_nurses_initially(client, head_nurse, nurses, auth_headers):
    resp = client.get("/api/ipd/nurse-workload", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    assert all(n["patient_count"] == 0 for n in data)


def test_nurse_workload_reflects_current_assignment_counts(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    for i in range(3):
        pid = _admit(client, auth_headers, head_nurse, name=f"Load Patient {i}", bed=str(i))
        client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=h)
    pid_other = _admit(client, auth_headers, head_nurse, name="Load Patient Other", bed="other")
    client.post("/api/ipd/assign", json={"patient_id": pid_other, "nurse_id": nurses[1].id}, headers=h)

    workload = {n["id"]: n["patient_count"] for n in client.get("/api/ipd/nurse-workload", headers=h).json()}
    assert workload[nurses[0].id] == 3
    assert workload[nurses[1].id] == 1
    assert workload[nurses[2].id] == 0
    assert workload[nurses[3].id] == 0


def test_nurse_workload_decreases_after_unassign(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse)
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=h)
    before = {n["id"]: n["patient_count"] for n in client.get("/api/ipd/nurse-workload", headers=h).json()}
    assert before[nurses[0].id] == 1
    client.post("/api/ipd/unassign", json={"patient_id": pid}, headers=h)
    after = {n["id"]: n["patient_count"] for n in client.get("/api/ipd/nurse-workload", headers=h).json()}
    assert after[nurses[0].id] == 0


def test_nurse_workload_does_not_double_count_after_reassignment(client, head_nurse, nurses, auth_headers):
    """Reassigning closes the prior assignment -- the old nurse's count must drop to 0, not
    stay at 1 alongside the new nurse's count also being 1 (which would double-count)."""
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse)
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=h)
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[1].id}, headers=h)
    workload = {n["id"]: n["patient_count"] for n in client.get("/api/ipd/nurse-workload", headers=h).json()}
    assert workload[nurses[0].id] == 0
    assert workload[nurses[1].id] == 1


def test_nurse_workload_excludes_nurses_from_other_organizations(client, head_nurse, make_user, auth_headers):
    make_user(email="foreign-nurse@hn-admit-assign.com", role="Nurse")  # different org
    workload = client.get("/api/ipd/nurse-workload", headers=auth_headers(head_nurse)).json()
    assert all("foreign-nurse" not in n["email"] for n in workload)


def test_nurse_workload_excludes_discharged_patients(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    pid = _admit(client, auth_headers, head_nurse)
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[0].id}, headers=h)
    client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=h)
    workload = {n["id"]: n["patient_count"] for n in client.get("/api/ipd/nurse-workload", headers=h).json()}
    assert workload[nurses[0].id] == 0, "discharge closes the assignment, so workload must drop even though the Patient row still exists"


@pytest.mark.parametrize("role", ["Nurse", "NursingStation", "Doctor", "Admin"])
def test_only_headnurse_can_view_nurse_workload(client, head_nurse, make_user, auth_headers, role):
    other = make_user(email=f"{role.lower()}@hn-admit-assign.com", role=role, organization_id=head_nurse.organization_id)
    resp = client.get("/api/ipd/nurse-workload", headers=auth_headers(other))
    assert resp.status_code == 403


def test_nurse_workload_empty_list_when_no_nurses_in_org(client, make_user, auth_headers):
    lonely_head = make_user(email="lonely-head@hn-admit-assign.com", role="HeadNurse")
    resp = client.get("/api/ipd/nurse-workload", headers=auth_headers(lonely_head))
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Assigning a large ward's worth of patients across several nurses (busy-day scale)
# ---------------------------------------------------------------------------

def test_headnurse_assigns_twenty_patients_across_four_nurses(client, head_nurse, nurses, auth_headers):
    h = auth_headers(head_nurse)
    patient_ids = [_admit(client, auth_headers, head_nurse, name=f"Scale Patient {i}", bed=str(i)) for i in range(20)]
    for i, pid in enumerate(patient_ids):
        client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[i % 4].id}, headers=h)

    workload = {n["id"]: n["patient_count"] for n in client.get("/api/ipd/nurse-workload", headers=h).json()}
    assert all(count == 5 for count in workload.values())
    assert sum(workload.values()) == 20
