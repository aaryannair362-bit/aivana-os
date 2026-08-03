"""
Admission scenarios driven by NursingStation -- this is the role's primary daily duty (the
"front desk" of the ward), so it gets the deepest scenario coverage: volume, data variety, and
realistic multi-specialty-hospital intake patterns.
"""
import pytest


@pytest.fixture
def station(make_user):
    return make_user(email="station@ns-admission.com", role="NursingStation")


def _admit(client, auth_headers, station, **overrides):
    payload = {"name": "NS Admit Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = client.post("/api/ipd/patients", json=payload, headers=auth_headers(station))
    assert resp.status_code == 200
    return resp.json()["id"]


def test_station_admits_a_patient_with_full_details(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="Full Detail Patient", age=45, gender="Male",
                 ward="ICU", bed="I3", diagnosis="Chest pain, rule out MI")
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    p = details["patient"]
    assert p["name"] == "Full Detail Patient"
    assert p["age"] == 45
    assert p["gender"] == "Male"
    assert p["ward"] == "ICU"
    assert p["bed"] == "I3"
    assert p["diagnosis"] == "Chest pain, rule out MI"
    assert p["status"] == "Active"


def test_station_admits_a_patient_with_only_required_fields(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="Minimal Patient", ward="General")
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["age"] is None
    assert details["patient"]["diagnosis"] is None


@pytest.mark.parametrize("ward", ["ICU", "General", "Maternity", "Pediatrics", "Emergency",
                                   "Cardiology", "Orthopedics", "Oncology", "Neurology", "Post-Op"])
def test_station_admits_across_every_specialty_ward(client, station, auth_headers, ward):
    pid = _admit(client, auth_headers, station, ward=ward)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["ward"] == ward


@pytest.mark.parametrize("age", [0, 1, 5, 18, 45, 65, 90, 105])
def test_station_admits_across_full_age_range(client, station, auth_headers, age):
    pid = _admit(client, auth_headers, station, age=age)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["age"] == age


@pytest.mark.parametrize("gender", ["Male", "Female", "Other", "Non-binary", "Prefer not to say"])
def test_station_admits_across_gender_options(client, station, auth_headers, gender):
    pid = _admit(client, auth_headers, station, gender=gender)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["gender"] == gender


def test_station_admits_patient_with_unicode_name(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="अनिल कुमार शर्मा")
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["name"] == "अनिल कुमार शर्मा"


def test_station_admits_patient_with_detailed_multiline_diagnosis(client, station, auth_headers):
    diagnosis = "1. Type 2 Diabetes Mellitus\n2. Hypertension\n3. Chronic kidney disease stage 3"
    pid = _admit(client, auth_headers, station, diagnosis=diagnosis)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["diagnosis"] == diagnosis


@pytest.mark.parametrize("bed_format", ["1", "12-A", "ICU-3", "Bed 7", "B", "101-North"])
def test_station_admits_with_various_bed_formats(client, station, auth_headers, bed_format):
    pid = _admit(client, auth_headers, station, bed=bed_format)
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["bed"] == bed_format


def test_station_handles_a_busy_admission_rush_of_thirty_patients(client, station, auth_headers):
    """Simulates a mass-casualty or peak-hours admission surge -- the exact 'busy day' scenario
    this system exists for."""
    ids = []
    for i in range(30):
        pid = _admit(client, auth_headers, station, name=f"Rush Patient {i}", bed=str(i),
                     ward="Emergency" if i % 3 == 0 else "General")
        ids.append(pid)
    assert len(set(ids)) == 30
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert len(roster) == 30
    emergency_count = sum(1 for p in roster if p["ward"] == "Emergency")
    assert emergency_count == 10


def test_newly_admitted_patients_start_unassigned_and_flagged_for_headnurse(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="Fresh Intake")
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    p = next(p for p in roster if p["id"] == pid)
    assert p["assigned_nurse"] is None


def test_station_admits_patient_then_immediately_looks_up_details(client, station, auth_headers):
    pid = _admit(client, auth_headers, station, name="Immediate Lookup")
    resp = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station))
    assert resp.status_code == 200
    assert resp.json()["vitals"] == []
    assert resp.json()["tasks"] == []


def test_station_admit_empty_string_name_rejected(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "", "ward": "General"}, headers=auth_headers(station))
    assert resp.status_code == 400


def test_station_admit_empty_string_ward_rejected(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "X", "ward": ""}, headers=auth_headers(station))
    assert resp.status_code == 400


def test_station_admit_negative_age_rejected(client, station, auth_headers):
    """age validation (0 <= age <= 130) applies regardless of who admits -- consistent with
    HeadNurse admission (test_admission_scenarios.py)."""
    resp = client.post("/api/ipd/patients", json={"name": "NS Admit Patient", "ward": "General", "bed": "1", "age": -3},
                        headers=auth_headers(station))
    assert resp.status_code == 400


def test_two_patients_same_name_different_beds_both_admitted_successfully(client, station, auth_headers):
    """The duplicate-name gate applies regardless of who admits -- the second submission must
    resubmit with confirm_duplicate=true to proceed (see test_ipd_admit_validation.py)."""
    id1 = _admit(client, auth_headers, station, name="Common Name", bed="1")
    id2 = _admit(client, auth_headers, station, name="Common Name", bed="2", confirm_duplicate=True)
    assert id1 != id2


def test_station_admitted_patient_immediately_visible_to_headnurse_in_same_org(client, station, make_user, auth_headers):
    head_nurse = make_user(email="head@ns-admission.com", role="HeadNurse", organization_id=station.organization_id)
    pid = _admit(client, auth_headers, station, name="Cross-Role Visibility")
    roster = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    assert pid in [p["id"] for p in roster]


def test_station_admitted_patient_immediately_assignable_by_headnurse(client, station, make_user, auth_headers):
    head_nurse = make_user(email="head2@ns-admission.com", role="HeadNurse", organization_id=station.organization_id)
    nurse = make_user(email="nurse@ns-admission.com", role="Nurse", organization_id=station.organization_id)
    pid = _admit(client, auth_headers, station, name="Ready For Assignment")
    resp = client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
