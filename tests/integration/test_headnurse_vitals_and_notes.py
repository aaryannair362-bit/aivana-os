"""
Manual (non-voice) vitals recording and nursing-note authoring as HeadNurse, plus patient-
detail/chart review. Complements test_headnurse_voice_features.py (voice path) and
test_ipd_edge_cases.py (boundary values, generic actor) with HeadNurse-specific depth.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-vitals-notes.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@hn-vitals-notes.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "HN Vitals Patient", "ward": "General", "bed": "V1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Manual vitals recording
# ---------------------------------------------------------------------------

def test_headnurse_records_full_vitals_manually(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "bp_systolic": 120, "bp_diastolic": 80,
                                                  "heart_rate": 72, "temperature": 37.0, "oxygen_sat": 98,
                                                  "respiratory_rate": 16, "notes": "Routine check"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_records_vitals_on_patient_with_no_assignment(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 75}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_records_vitals_on_patient_assigned_to_a_different_nurse(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 90}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


@pytest.mark.parametrize("recorded_by_role", ["head_nurse", "nurse"])
def test_recorded_vital_correctly_attributes_the_actual_recorder(client, head_nurse, nurse, patient_id, auth_headers, recorded_by_role):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    actor = head_nurse if recorded_by_role == "head_nurse" else nurse
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 77}, headers=auth_headers(actor))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["vitals"][0]["nurse_email"] == actor.email


def test_headnurse_records_a_full_days_worth_of_vitals_readings(client, head_nurse, patient_id, auth_headers):
    readings = [(72, 37.0), (75, 37.2), (80, 37.5), (110, 38.5), (95, 37.8)]
    for hr, temp in readings:
        resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": hr, "temperature": temp},
                            headers=auth_headers(head_nurse))
        assert resp.status_code == 200
    vitals = client.get(f"/api/ipd/vitals/{patient_id}?limit=10", headers=auth_headers(head_nurse)).json()
    assert len(vitals) == 5
    assert vitals[0]["heart_rate"] == 95  # most recent first


def test_headnurse_sees_abnormal_flag_update_in_real_time_after_recording(client, head_nurse, patient_id, auth_headers):
    roster_before = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    assert roster_before[0]["abnormal"] is False
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "bp_systolic": 160}, headers=auth_headers(head_nurse))
    roster_after = client.get("/api/ipd/patients", headers=auth_headers(head_nurse)).json()
    assert roster_after[0]["abnormal"] is True


@pytest.mark.parametrize("field,value", [
    ("bp_systolic", 200), ("bp_diastolic", 120), ("heart_rate", 150),
    ("temperature", 40.5), ("oxygen_sat", 85), ("respiratory_rate", 30),
])
def test_headnurse_records_various_critical_readings_across_all_fields(client, head_nurse, patient_id, auth_headers, field, value):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, field: value}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(head_nurse)).json()[0]
    assert saved[field] == value


def test_headnurse_empty_vital_submission_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id}, headers=auth_headers(head_nurse))
    assert resp.status_code == 422


def test_headnurse_vitals_for_nonexistent_patient_404(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"patient_id": 999999, "heart_rate": 80}, headers=auth_headers(head_nurse))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Manual nursing notes
# ---------------------------------------------------------------------------

def test_headnurse_writes_full_soap_note_manually(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "Reports better sleep",
                                                     "objective": "Vitals within normal limits", "assessment": "Stable",
                                                     "plan": "Continue current management"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_writes_note_on_unassigned_patient(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "Fine", "objective": "",
                                                     "assessment": "", "plan": ""}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_note_empty_submission_rejected(client, head_nurse, patient_id, auth_headers):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "", "objective": "",
                                                     "assessment": "", "plan": ""}, headers=auth_headers(head_nurse))
    assert resp.status_code == 422


def test_headnurse_writes_notes_for_several_different_patients(client, head_nurse, auth_headers):
    pids = []
    for i in range(4):
        resp = client.post("/api/ipd/patients", json={"name": f"Notes Patient {i}", "ward": "General", "bed": str(i)},
                            headers=auth_headers(head_nurse))
        pids.append(resp.json()["id"])
    for pid in pids:
        resp = client.post("/api/nursing-notes", json={"patient_id": pid, "subjective": f"Note for patient {pid}",
                                                         "objective": "", "assessment": "", "plan": ""},
                            headers=auth_headers(head_nurse))
        assert resp.status_code == 200
    for pid in pids:
        details = client.get(f"/api/patients/{pid}/details", headers=auth_headers(head_nurse)).json()
        assert len(details["nursing_notes"]) == 1
        assert f"patient {pid}" in details["nursing_notes"][0]["notes"]


# ---------------------------------------------------------------------------
# Patient detail / chart review as HeadNurse (read access to everything: vitals, tasks,
# doctor's consultations, nursing notes -- across every nurse and every source)
# ---------------------------------------------------------------------------

def test_headnurse_sees_the_full_chart_regardless_of_who_recorded_what(client, head_nurse, nurse, patient_id, auth_headers):
    client.post("/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 80}, headers=auth_headers(nurse))
    client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 85}, headers=auth_headers(head_nurse))
    client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "By nurse", "objective": "",
                                              "assessment": "", "plan": ""}, headers=auth_headers(nurse))
    client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "By head nurse", "objective": "",
                                              "assessment": "", "plan": ""}, headers=auth_headers(head_nurse))

    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert len(details["vitals"]) == 2
    assert len(details["nursing_notes"]) == 2
    recorders = {v["nurse_email"] for v in details["vitals"]}
    assert recorders == {nurse.email, head_nurse.email}


def test_headnurse_views_doctors_opd_consultations_linked_to_the_patient(client, head_nurse, make_user, patient_id, auth_headers, monkeypatch, db_session):
    from app.models import Consultation
    doctor = make_user(email="doc@hn-vitals-notes.com", role="Doctor", organization_id=head_nurse.organization_id)
    consultation = Consultation(case_id="20260101-abcdef", patient_id=patient_id,
                                 organization_id=head_nurse.organization_id, user_id=doctor.id,
                                 chief_complaint="Fever", primary_diagnosis="Viral infection")
    db_session.add(consultation)
    db_session.commit()
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert len(details["consultations"]) == 1
    assert details["consultations"][0]["chief_complaint"] == "Fever"


def test_headnurse_edits_patient_ward_bed_diagnosis(client, head_nurse, patient_id, auth_headers):
    resp = client.put(f"/api/patients/{patient_id}", json={"ward": "ICU", "bed": "ICU-3", "diagnosis": "Sepsis, transferred to ICU"},
                       headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert details["patient"]["ward"] == "ICU"
    assert details["patient"]["bed"] == "ICU-3"


def test_headnurse_partial_edit_only_updates_provided_fields(client, head_nurse, patient_id, auth_headers):
    original = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()["patient"]
    client.put(f"/api/patients/{patient_id}", json={"diagnosis": "Updated diagnosis only"}, headers=auth_headers(head_nurse))
    updated = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()["patient"]
    assert updated["diagnosis"] == "Updated diagnosis only"
    assert updated["ward"] == original["ward"]
    assert updated["bed"] == original["bed"]
