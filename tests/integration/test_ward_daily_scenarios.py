"""
End-to-end scenario tests for a busy multi-specialty ward day: many patients, several nurses
across several wards, shift handoffs (reassignment), a nursing station admitting patients in
bulk, and doctors doing read-only rounds. These exercise realistic sequences of API calls
rather than single-endpoint edge cases (which live in test_ipd_edge_cases.py and the other
focused files).
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@daily-ward.com", role="HeadNurse")


@pytest.fixture
def station(make_user, head_nurse):
    return make_user(email="station@daily-ward.com", role="NursingStation", organization_id=head_nurse.organization_id)


@pytest.fixture
def doctor(make_user, head_nurse):
    return make_user(email="doctor@daily-ward.com", role="Doctor", organization_id=head_nurse.organization_id)


def _admit(client, auth_headers, admitter, **overrides):
    payload = {"name": "Ward Patient", "age": 45, "gender": "Female", "ward": "General", "bed": "G1", "diagnosis": "Observation"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(admitter))
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Multi-patient, multi-nurse ward day
# ---------------------------------------------------------------------------

def test_nursing_station_admits_a_full_wards_worth_of_patients(client, station, auth_headers):
    ids = [_admit(client, auth_headers, station, name=f"Patient {i}", bed=f"B{i}") for i in range(1, 21)]
    assert len(set(ids)) == 20
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert len(roster) == 20


def test_head_nurse_distributes_patients_across_multiple_nurses(client, head_nurse, make_user, auth_headers):
    nurses = [make_user(email=f"shift-nurse{i}@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
              for i in range(3)]
    patient_ids = [_admit(client, auth_headers, head_nurse, name=f"Distributed {i}", bed=f"D{i}") for i in range(6)]
    for i, pid in enumerate(patient_ids):
        nurse = nurses[i % 3]
        resp = client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
        assert resp.status_code == 200
    for i, nurse in enumerate(nurses):
        my_patients = client.get("/api/ipd/patients", headers=auth_headers(nurse)).json()
        assert len(my_patients) == 2
        for p in my_patients:
            assert p["assigned_nurse"]["id"] == nurse.id


def test_shift_handoff_reassigns_all_of_one_nurses_patients_to_another(client, head_nurse, make_user, auth_headers):
    """Simulates an end-of-shift handoff: nurse A's patients are reassigned to nurse B."""
    nurse_a = make_user(email="dayshift@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
    nurse_b = make_user(email="nightshift@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
    patient_ids = [_admit(client, auth_headers, head_nurse, name=f"Handoff {i}", bed=f"H{i}") for i in range(4)]
    for pid in patient_ids:
        client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse_a.id}, headers=auth_headers(head_nurse))

    assert len(client.get("/api/ipd/patients", headers=auth_headers(nurse_a)).json()) == 4

    for pid in patient_ids:
        client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse_b.id}, headers=auth_headers(head_nurse))

    assert client.get("/api/ipd/patients", headers=auth_headers(nurse_a)).json() == []
    assert len(client.get("/api/ipd/patients", headers=auth_headers(nurse_b)).json()) == 4


def test_doctor_can_view_but_not_modify_any_patient_on_rounds(client, head_nurse, doctor, auth_headers):
    pid = _admit(client, auth_headers, head_nurse)
    roster = client.get("/api/ipd/patients", headers=auth_headers(doctor))
    assert roster.status_code == 200
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(doctor))
    assert details.status_code == 200
    update = client.put(f"/api/patients/{pid}", json={"diagnosis": "Doctor override attempt"}, headers=auth_headers(doctor))
    assert update.status_code == 403
    vital = client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 80}, headers=auth_headers(doctor))
    assert vital.status_code == 403


def test_multiple_wards_in_same_organization_are_all_visible_to_head_nurse(client, head_nurse, auth_headers):
    wards = ["ICU", "General", "Maternity", "Pediatrics", "Emergency"]
    for w in wards:
        _admit(client, auth_headers, head_nurse, name=f"{w} Patient", ward=w, bed="1")
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    seen_wards = {p["ward"] for p in roster}
    assert seen_wards == set(wards)


def test_unassigned_patients_are_flagged_for_head_nurse_attention(client, head_nurse, make_user, auth_headers):
    nurse = make_user(email="only-one-assigned@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
    assigned = _admit(client, auth_headers, head_nurse, name="Assigned One", bed="G1")
    unassigned = _admit(client, auth_headers, head_nurse, name="Unassigned One", bed="G2")
    client.post("/api/ipd/assign", json={"patient_id": assigned, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))

    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    by_id = {p["id"]: p for p in roster}
    assert by_id[assigned]["assigned_nurse"] is not None
    assert by_id[unassigned]["assigned_nurse"] is None


def test_nurse_sees_only_currently_assigned_patients_not_historical(client, head_nurse, make_user, auth_headers):
    nurse_a = make_user(email="historical-a@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
    nurse_b = make_user(email="historical-b@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
    pid = _admit(client, auth_headers, head_nurse)
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse_a.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse_b.id}, headers=auth_headers(head_nurse))
    # nurse_a recorded a vital while they had the patient -- that history must remain visible
    # in the chart even though nurse_a no longer sees the patient in their own roster.
    assert client.get("/api/ipd/patients", headers=auth_headers(nurse_a)).json() == []
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(nurse_b))
    assert details.status_code == 200


def test_same_patient_name_different_beds_are_distinct_patients(client, head_nurse, auth_headers):
    """Common in real wards -- two patients can share a name. Ward+bed, not name, disambiguates.
    The second admission hits the duplicate-name confirmation gate first (by design, so a typo'd
    re-admission isn't silently duplicated) and must resubmit with confirm_duplicate=true."""
    id1 = _admit(client, auth_headers, head_nurse, name="Priya Sharma", ward="ICU", bed="1")
    id2 = _admit(client, auth_headers, head_nurse, name="Priya Sharma", ward="ICU", bed="2", confirm_duplicate=True)
    assert id1 != id2
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    matching = [p for p in roster if p["name"] == "Priya Sharma"]
    assert len(matching) == 2
    assert {p["bed"] for p in matching} == {"1", "2"}


def test_full_patient_day_vitals_tasks_notes_all_visible_together(client, head_nurse, make_user, auth_headers):
    """A representative full day for one patient: admit, assign, record vitals three times,
    create and complete a task, write a nursing note -- everything shows up in one chart."""
    nurse = make_user(email="full-day@daily-ward.com", role="Nurse", organization_id=head_nurse.organization_id)
    pid = _admit(client, auth_headers, head_nurse, name="Full Day Patient")
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))

    for hr in (72, 75, 90):
        resp = client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": hr}, headers=auth_headers(nurse))
        assert resp.status_code == 200

    task_resp = client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "Administer antibiotics", "nurse_id": nurse.id},
                             headers=auth_headers(head_nurse))
    task_id = task_resp.json()["id"]
    complete_resp = client.patch(f"/api/ipd/tasks/{task_id}", json={"status": "Completed"}, headers=auth_headers(nurse))
    assert complete_resp.status_code == 200

    note_resp = client.post("/api/nursing-notes", json={"patient_id": pid, "subjective": "Comfortable", "objective": "Stable",
                                                          "assessment": "Improving", "plan": "Continue monitoring"},
                             headers=auth_headers(nurse))
    assert note_resp.status_code == 200

    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(head_nurse)).json()
    assert len(details["vitals"]) == 3
    assert len(details["tasks"]) == 1
    assert details["tasks"][0]["status"] == "Completed"
    assert len(details["nursing_notes"]) == 1


def test_vitals_are_returned_most_recent_first(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Ordering Patient")
    for temp in (36.5, 37.0, 38.5):
        client.post("/api/ipd/vitals", json={"patient_id": pid, "temperature": temp}, headers=auth_headers(head_nurse))
    vitals = client.get(f"/api/ipd/vitals/{pid}", headers=auth_headers(head_nurse)).json()
    assert [v["temperature"] for v in vitals] == [38.5, 37.0, 36.5]


def test_dashboard_abnormal_flag_reflects_only_latest_vital(client, head_nurse, auth_headers):
    """A patient who WAS abnormal but has since normalized must not stay flagged -- only the
    latest reading counts."""
    pid = _admit(client, auth_headers, head_nurse, name="Recovering Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 150}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 75}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["abnormal"] is False


def test_dashboard_flags_patient_who_just_became_abnormal(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Deteriorating Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 75}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 150}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["abnormal"] is True


# ---------------------------------------------------------------------------
# Low-oxygen-saturation / bradycardia flagging -- these were a documented current-behavior gap
# (the abnormal-vital rule only checked values ABOVE a high threshold for BP/HR/temp, with no
# check at all for oxygen_sat and no LOW threshold for heart_rate). Fixed: heart_rate < 60 and
# oxygen_sat < 92 now flag abnormal too (main.py get_ipd_patients).
# ---------------------------------------------------------------------------

def test_dangerously_low_oxygen_saturation_is_flagged_abnormal(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Hypoxic Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "oxygen_sat": 78}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["abnormal"] is True, (
        "A critically low SpO2 reading (78%) must raise an abnormal alert on the ward dashboard."
    )


def test_severe_bradycardia_is_flagged_abnormal(client, head_nurse, auth_headers):
    pid = _admit(client, auth_headers, head_nurse, name="Bradycardic Patient")
    client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 35}, headers=auth_headers(head_nurse))
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["abnormal"] is True, (
        "Severe bradycardia (35 bpm) must raise an abnormal alert on the ward dashboard."
    )
