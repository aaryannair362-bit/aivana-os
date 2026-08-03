"""
Patient admission scenarios: unicode names/wards (a realistic requirement for an Indian
multi-specialty hospital), age/gender edge cases, and documented gaps around field-length and
type coercion that only bite in a real (Postgres) deployment, not the SQLite test DB.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@admission-scenarios.com", role="HeadNurse")


@pytest.fixture
def station(make_user, head_nurse):
    return make_user(email="station@admission-scenarios.com", role="NursingStation", organization_id=head_nurse.organization_id)


def test_admit_patient_with_unicode_name_and_ward(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "प्रिया शर्मा", "ward": "आईसीयू", "bed": "१"},
                        headers=auth_headers(station))
    assert resp.status_code == 200
    pid = resp.json()["id"]
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["name"] == "प्रिया शर्मा"
    assert details["patient"]["ward"] == "आईसीयू"


def test_admit_patient_with_emoji_in_diagnosis_notes(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Test Patient", "ward": "General", "bed": "E1",
                                                    "diagnosis": "Fracture 🦴 - needs surgery ⚠️"},
                        headers=auth_headers(station))
    assert resp.status_code == 200


@pytest.mark.parametrize("age", [0, 1, 120, 130])
def test_admit_patient_various_age_boundaries_accepted(client, station, auth_headers, age):
    resp = client.post("/api/ipd/patients", json={"name": f"Age Test {age}", "ward": "General", "bed": f"A-{age}", "age": age},
                        headers=auth_headers(station))
    assert resp.status_code == 200
    assert resp.json()["id"] is not None


def test_admit_patient_age_above_130_rejected(client, station, auth_headers):
    """age validation was added alongside the Ward model -- 130 is the accepted upper bound,
    131 and above is rejected (see test_ipd_admit_validation.py for the full validation suite)."""
    resp = client.post("/api/ipd/patients", json={"name": "Too Old", "ward": "General", "bed": "A2", "age": 150},
                        headers=auth_headers(station))
    assert resp.status_code == 400


def test_admit_newborn_age_zero(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Newborn", "ward": "Maternity", "bed": "N1", "age": 0},
                        headers=auth_headers(station))
    assert resp.status_code == 200
    pid = resp.json()["id"]
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["age"] == 0


def test_admit_patient_with_negative_age_rejected(client, station, auth_headers):
    """age validation (0 <= age <= 130) was added alongside the Ward model -- negative ages are
    now rejected, closing the gap this test used to document."""
    resp = client.post("/api/ipd/patients", json={"name": "Negative Age", "ward": "General", "bed": "N2", "age": -5},
                        headers=auth_headers(station))
    assert resp.status_code == 400


def test_admit_patient_missing_optional_fields(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Minimal Patient", "ward": "General"},
                        headers=auth_headers(station))
    assert resp.status_code == 200
    pid = resp.json()["id"]
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["patient"]["age"] is None
    assert details["patient"]["bed"] is None
    assert details["patient"]["diagnosis"] is None


@pytest.mark.parametrize("bed", ["12-A", "ICU-3", "B", "101", "Bed #7", ""])
def test_admit_patient_various_bed_formats(client, station, auth_headers, bed):
    resp = client.post("/api/ipd/patients", json={"name": "Bed Format Test", "ward": "General", "bed": bed},
                        headers=auth_headers(station))
    assert resp.status_code == 200


@pytest.mark.parametrize("gender", ["Male", "Female", "Other", "Non-binary", "Prefer not to say", ""])
def test_admit_patient_various_gender_values(client, station, auth_headers, gender):
    resp = client.post("/api/ipd/patients", json={"name": "Gender Test", "ward": "General", "bed": "G1", "gender": gender},
                        headers=auth_headers(station))
    assert resp.status_code == 200


def test_admit_patient_with_very_long_name(client, station, auth_headers):
    """Patient.name is String(200). SQLite (this test DB) does not enforce VARCHAR length at
    all, so this passes here regardless of length -- production Postgres DOES enforce it and
    would raise a raw 500 for a name over 200 chars. Not independently verified against a real
    Postgres instance (see ARCHITECTURE_NOTES.md's DATABASE_URL safety note); flagged as an
    environment-parity risk, not silently 'fixed' with an invented truncation/validation rule."""
    long_name = "A" * 300
    resp = client.post("/api/ipd/patients", json={"name": long_name, "ward": "General", "bed": "L1"},
                        headers=auth_headers(station))
    assert resp.status_code == 200


def test_admit_patient_empty_string_name_rejected(client, station, auth_headers):
    """An empty string is falsy in Python, so it's caught by the same `if not name` check as a
    missing field entirely."""
    resp = client.post("/api/ipd/patients", json={"name": "", "ward": "General"}, headers=auth_headers(station))
    assert resp.status_code == 400


def test_admit_patient_empty_string_ward_rejected(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "No Ward Patient", "ward": ""}, headers=auth_headers(station))
    assert resp.status_code == 400


def test_admit_patient_whitespace_only_name_accepted(client, station, auth_headers):
    """Documents current behavior: whitespace is truthy in Python (`not "   "` is False), so a
    whitespace-only name passes the presence check -- no .strip() is applied server-side."""
    resp = client.post("/api/ipd/patients", json={"name": "   ", "ward": "General"}, headers=auth_headers(station))
    assert resp.status_code == 200


def test_admit_many_patients_same_day_all_independently_retrievable(client, station, auth_headers):
    ids = []
    for i in range(30):
        resp = client.post("/api/ipd/patients", json={"name": f"Bulk Patient {i}", "ward": "General", "bed": str(i)},
                            headers=auth_headers(station))
        ids.append(resp.json()["id"])
    assert len(set(ids)) == 30
    for pid in ids[:5]:
        assert client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).status_code == 200


def test_head_nurse_can_also_admit_patients(client, head_nurse, auth_headers):
    """Both HeadNurse and NursingStation are allowed to admit -- not NursingStation exclusively."""
    resp = client.post("/api/ipd/patients", json={"name": "Head Nurse Admit", "ward": "General", "bed": "HN1"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_newly_admitted_patient_immediately_visible_in_roster(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Just Admitted", "ward": "Emergency", "bed": "E5"},
                        headers=auth_headers(station))
    pid = resp.json()["id"]
    roster = client.get("/api/ipd/patients", headers=auth_headers(station)).json()
    assert pid in [p["id"] for p in roster]


def test_newly_admitted_patient_has_no_vitals_tasks_or_notes(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Fresh Admit", "ward": "General", "bed": "F1"},
                        headers=auth_headers(station))
    pid = resp.json()["id"]
    details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(station)).json()
    assert details["vitals"] == []
    assert details["tasks"] == []
    assert details["nursing_notes"] == []
    assert details["consultations"] == []
