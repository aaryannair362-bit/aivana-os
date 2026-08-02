"""
Regression tests for the nurse-consult "Process" persistence bug (see CHANGELOG.md).

The real ward workflow is a two-step review: mic -> "Process" (POST /api/ipd/nurse-consult
extracts vitals/labs/a draft SOAP note from a voice transcript) -> the nurse edits the draft in
the UI -> "Save" (separate POST /api/ipd/vitals + POST /api/nursing-notes calls persist exactly
what was reviewed). Before this fix, /api/ipd/nurse-consult itself inserted a Vital per
extracted item (with every structured column left null) and a NursingNote immediately, on
every "Process" click -- so a nurse who processed, edited, and saved ended up with TWO
records per consult (a raw AI draft nobody reviewed, plus the edited one), and a nurse who
processed and then cancelled without saving still left a permanent, un-reviewed ghost record
in the chart. Fixed by making nurse-consult a pure extraction/preview endpoint with no DB writes.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@consult-persist.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@consult-persist.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post(
        "/api/ipd/patients",
        json={"name": "Consult Persist Patient", "ward": "General", "bed": "C1"},
        headers=auth_headers(head_nurse),
    )
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


def _db_counts(db_session):
    from app.models import Vital, NursingNote
    return db_session.query(Vital).count(), db_session.query(NursingNote).count()


def test_process_does_not_write_any_vital_rows(client, nurse, patient_id, auth_headers, monkeypatch, db_session):
    mock_groq_json(monkeypatch, {
        "vitals": [{"parameter": "BP", "value": "120/80", "unit": "mmHg"},
                   {"parameter": "HR", "value": "72", "unit": "bpm"}],
        "labs": [{"test": "Hb", "result": "12.5"}],
        "nursing_note": {"subjective": "Headache", "objective": "Alert", "assessment": "Stable", "plan": "Monitor"},
    })
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "BP 120 over 80, HR 72, Hb 12.5"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    vitals_count, notes_count = _db_counts(db_session)
    assert vitals_count == 0, "nurse-consult must not insert Vital rows -- it's a preview step, Save is the persist step"
    assert notes_count == 0, "nurse-consult must not insert a NursingNote -- it's a preview step, Save is the persist step"


def test_process_returns_extracted_data_for_review(client, nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {
        "vitals": [{"parameter": "BP", "value": "120/80", "unit": "mmHg"}],
        "labs": [{"test": "WBC", "result": "8000"}],
        "nursing_note": {"subjective": "Cough", "objective": "", "assessment": "", "plan": "Rest"},
    })
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "Patient has a cough, BP 120/80, WBC 8000, advise rest"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    data = resp.json()
    assert data["vitals"] == [{"parameter": "BP", "value": "120/80", "unit": "mmHg"}]
    assert data["labs"] == [{"test": "WBC", "result": "8000"}]
    assert data["nursing_note"]["subjective"] == "Cough"


def test_calling_process_twice_still_writes_nothing(client, nurse, patient_id, auth_headers, monkeypatch, db_session):
    """A nurse who re-speaks/re-processes before Save must not accumulate ghost records."""
    mock_groq_json(monkeypatch, {"vitals": [{"parameter": "HR", "value": "80", "unit": "bpm"}], "labs": [], "nursing_note": {}})
    client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "heart rate eighty"}, headers=auth_headers(nurse))
    client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "heart rate eighty, take two"}, headers=auth_headers(nurse))
    vitals_count, notes_count = _db_counts(db_session)
    assert vitals_count == 0
    assert notes_count == 0


def test_processing_without_ever_saving_leaves_no_trace(client, nurse, patient_id, auth_headers, monkeypatch):
    """A nurse who processes, dislikes the draft, and closes the modal without Save must not
    have anything persisted -- confirmed via the patient details endpoint, not just a row count."""
    mock_groq_json(monkeypatch, {"vitals": [{"parameter": "Temp", "value": "38.5", "unit": "C"}], "labs": [],
                                  "nursing_note": {"subjective": "Fever", "objective": "", "assessment": "", "plan": ""}})
    client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "temperature 38.5, patient reports fever"},
                headers=auth_headers(nurse))
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(nurse)).json()
    assert details["vitals"] == []
    assert details["nursing_notes"] == []


def test_save_after_process_persists_exactly_once(client, nurse, patient_id, auth_headers, monkeypatch, db_session):
    """The full real flow: Process (preview only) then Save (the two actual persist calls the
    frontend issues) results in exactly one Vital and one NursingNote -- not zero, not two."""
    mock_groq_json(monkeypatch, {
        "vitals": [{"parameter": "Heart Rate", "value": "88", "unit": "bpm"}],
        "labs": [], "nursing_note": {"subjective": "Fine", "objective": "Alert", "assessment": "Stable", "plan": "None"},
    })
    process_resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "HR 88, patient fine"},
                                headers=auth_headers(nurse))
    assert process_resp.status_code == 200

    # Save step: the frontend now sends ONE consolidated, mapped vitals POST (see
    # mapVitalsToStructured in ipd.html) plus the reviewed SOAP note.
    save_vital = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 88,
                                                        "bp_systolic": None, "bp_diastolic": None,
                                                        "temperature": None, "oxygen_sat": None,
                                                        "respiratory_rate": None, "notes": ""},
                              headers=auth_headers(nurse))
    assert save_vital.status_code == 200
    save_note = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "Fine",
                                                          "objective": "Alert", "assessment": "Stable", "plan": "None"},
                             headers=auth_headers(nurse))
    assert save_note.status_code == 200

    vitals_count, notes_count = _db_counts(db_session)
    assert vitals_count == 1
    assert notes_count == 1


def test_nurse_consult_requires_patient_id(client, nurse, auth_headers):
    resp = client.post("/api/ipd/nurse-consult", json={"voice_text": "BP 120/80"}, headers=auth_headers(nurse))
    assert resp.status_code == 400


def test_nurse_consult_requires_voice_text(client, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id}, headers=auth_headers(nurse))
    assert resp.status_code == 400


def test_nurse_consult_blocks_unassigned_nurse(client, make_user, head_nurse, patient_id, auth_headers, monkeypatch):
    other_nurse = make_user(email="other-nurse@consult-persist.com", role="Nurse", organization_id=head_nurse.organization_id)
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "BP 120/80"},
                        headers=auth_headers(other_nurse))
    assert resp.status_code == 403


def test_nurse_consult_blocks_doctor(client, make_user, head_nurse, patient_id, auth_headers, monkeypatch):
    doctor = make_user(email="doc@consult-persist.com", role="Doctor", organization_id=head_nurse.organization_id)
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "BP 120/80"},
                        headers=auth_headers(doctor))
    assert resp.status_code == 403


def test_nurse_consult_for_nonexistent_patient_returns_404(client, nurse, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": 999999, "voice_text": "BP 120/80"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 404


def test_nurse_consult_handles_empty_extraction_gracefully(client, nurse, patient_id, auth_headers, monkeypatch):
    """Unlike record_vital/create_nursing_note, nurse-consult is preview-only and never persists,
    so a totally-empty extraction is safe to just return as-is (the frontend's own Save-time
    "nothing to save" guard is what stops an empty save, not this endpoint)."""
    mock_groq_json(monkeypatch, "not valid json at all")
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "mumble mumble unintelligible"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    data = resp.json()
    assert data["vitals"] == []
    assert data["labs"] == []
