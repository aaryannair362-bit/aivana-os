"""
Vitals-recording scenarios beyond the abnormal-threshold boundaries already covered in
test_ipd_edge_cases.py: decimal precision, the get_vitals `limit` query param, multi-patient
isolation, unicode/long notes, and documented gaps in numeric-type coercion.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@vitals-scenarios.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@vitals-scenarios.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Vitals Scenario Patient", "ward": "General", "bed": "V1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


@pytest.mark.parametrize("temperature", [35.0, 36.6, 37.55, 39.9, 41.2, 30.0])
def test_decimal_temperature_precision_preserved(client, nurse, patient_id, auth_headers, temperature):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "temperature": temperature}, headers=auth_headers(nurse))
    assert resp.status_code == 200
    vitals = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()
    assert vitals[0]["temperature"] == temperature


@pytest.mark.parametrize("limit,recorded_count,expected_returned", [
    (10, 3, 3),
    (2, 5, 2),
    (1, 5, 1),
    (100, 5, 5),
])
def test_get_vitals_limit_param(client, nurse, patient_id, auth_headers, limit, recorded_count, expected_returned):
    for i in range(recorded_count):
        client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 70 + i}, headers=auth_headers(nurse))
    vitals = client.get(f"/api/ipd/vitals/{patient_id}?limit={limit}", headers=auth_headers(nurse)).json()
    assert len(vitals) == expected_returned


def test_get_vitals_default_limit_is_ten(client, nurse, patient_id, auth_headers):
    for i in range(15):
        client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 60 + i}, headers=auth_headers(nurse))
    vitals = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()
    assert len(vitals) == 10


def test_vitals_do_not_leak_between_two_patients_of_the_same_nurse(client, head_nurse, nurse, auth_headers):
    p1 = client.post("/api/ipd/patients", json={"name": "Patient One", "ward": "General", "bed": "M1"},
                      headers=auth_headers(head_nurse)).json()["id"]
    p2 = client.post("/api/ipd/patients", json={"name": "Patient Two", "ward": "General", "bed": "M2"},
                      headers=auth_headers(head_nurse)).json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": p1, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/assign", json={"patient_id": p2, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))

    client.post("/api/ipd/vitals", json={"patient_id": p1, "heart_rate": 111}, headers=auth_headers(nurse))
    client.post("/api/ipd/vitals", json={"patient_id": p2, "heart_rate": 222}, headers=auth_headers(nurse))

    v1 = client.get(f"/api/ipd/vitals/{p1}", headers=auth_headers(nurse)).json()
    v2 = client.get(f"/api/ipd/vitals/{p2}", headers=auth_headers(nurse)).json()
    assert [v["heart_rate"] for v in v1] == [111]
    assert [v["heart_rate"] for v in v2] == [222]


def test_vital_notes_with_unicode_and_emoji_preserved(client, nurse, patient_id, auth_headers):
    note = "Patient reports दर्द (pain) in left arm 😖, requests पानी (water)"
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 80, "notes": note},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    vitals = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()
    assert vitals[0]["notes"] == note


def test_vital_notes_very_long_text_preserved(client, nurse, patient_id, auth_headers):
    note = "Detailed observation. " * 200  # ~4600 chars; notes is a Text column, unbounded
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 80, "notes": note},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    vitals = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()
    assert vitals[0]["notes"] == note


@pytest.mark.parametrize("field,value", [
    ("heart_rate", 999),
    ("bp_systolic", 500),
    ("respiratory_rate", 200),
    ("oxygen_sat", 150),  # >100% is physiologically impossible for a percentage
])
def test_physiologically_impossible_extreme_values_accepted_without_validation(client, nurse, patient_id, auth_headers, field, value):
    """Documents current behavior (consistent with test_ipd_edge_cases.py's negative-value gap):
    no upper-bound sanity check exists on any vital field, including oxygen_sat where >100% is
    impossible for a percentage reading."""
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, field: value}, headers=auth_headers(nurse))
    assert resp.status_code == 200
    vitals = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()
    assert vitals[0][field] == value


def test_multiple_nurses_recording_vitals_for_different_patients_same_ward(client, head_nurse, make_user, auth_headers):
    nurse_a = make_user(email="ward-a@vitals-scenarios.com", role="Nurse", organization_id=head_nurse.organization_id)
    nurse_b = make_user(email="ward-b@vitals-scenarios.com", role="Nurse", organization_id=head_nurse.organization_id)
    pa = client.post("/api/ipd/patients", json={"name": "Ward A Patient", "ward": "ICU", "bed": "1"},
                      headers=auth_headers(head_nurse)).json()["id"]
    pb = client.post("/api/ipd/patients", json={"name": "Ward B Patient", "ward": "ICU", "bed": "2"},
                      headers=auth_headers(head_nurse)).json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pa, "nurse_id": nurse_a.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/assign", json={"patient_id": pb, "nurse_id": nurse_b.id}, headers=auth_headers(head_nurse))

    assert client.post("/api/ipd/vitals", json={"patient_id": pa, "heart_rate": 80}, headers=auth_headers(nurse_a)).status_code == 200
    assert client.post("/api/ipd/vitals", json={"patient_id": pb, "heart_rate": 90}, headers=auth_headers(nurse_b)).status_code == 200
    # nurse_a must not be able to record vitals for nurse_b's patient
    assert client.post("/api/ipd/vitals", json={"patient_id": pb, "heart_rate": 100}, headers=auth_headers(nurse_a)).status_code == 403


def test_recording_vital_for_patient_not_yet_assigned_to_anyone_blocked_for_nurse(client, head_nurse, nurse, auth_headers):
    pid = client.post("/api/ipd/patients", json={"name": "Unassigned Vital Patient", "ward": "General", "bed": "U1"},
                       headers=auth_headers(head_nurse)).json()["id"]
    resp = client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 80}, headers=auth_headers(nurse))
    assert resp.status_code == 403


def test_head_nurse_can_record_vitals_for_any_patient_without_explicit_assignment(client, head_nurse, auth_headers):
    """HeadNurse bypasses the per-nurse assignment check entirely (only is_nurse() triggers it)."""
    pid = client.post("/api/ipd/patients", json={"name": "HeadNurse Direct Patient", "ward": "General", "bed": "H1"},
                       headers=auth_headers(head_nurse)).json()["id"]
    resp = client.post("/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 80}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


@pytest.mark.parametrize("bad_patient_id", [0, -1, "not-a-number"])
def test_record_vital_malformed_patient_id_handled_cleanly(client, nurse, auth_headers, bad_patient_id):
    resp = client.post("/api/ipd/vitals", json={"patient_id": bad_patient_id, "heart_rate": 80}, headers=auth_headers(nurse))
    assert resp.status_code in (400, 404, 422), (
        f"patient_id={bad_patient_id!r} produced an unhandled 500: {resp.status_code} {resp.text}"
    )
