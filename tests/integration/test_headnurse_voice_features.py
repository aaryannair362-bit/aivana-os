"""
Voice-based feature coverage specifically as the HeadNurse actor. The earlier voice-hardening
pass (test_voice_*.py) predominantly used a Nurse fixture; HeadNurse is equally entitled to use
every voice endpoint (record_vital, create_nursing_note, nurse-consult, voice-to-vitals) and,
unlike Nurse, is never subject to the per-patient assignment check -- this file confirms the
full voice feature set works identically well for HeadNurse, including on patients with no
nurse assigned at all.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-voice.com", role="HeadNurse")


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    """Deliberately never assigned to any nurse -- proving HeadNurse's voice access doesn't
    depend on assignment state at all."""
    resp = client.post("/api/ipd/patients", json={"name": "HN Voice Patient", "ward": "General", "bed": "V1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Voice vitals recording as HeadNurse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("voice_text,extraction", [
    ("BP one thirty over eighty five, heart rate seventy eight",
     {"bp_systolic": 130, "bp_diastolic": 85, "heart_rate": 78, "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""}),
    ("temperature is thirty eight point one, patient feels warm",
     {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None, "temperature": 38.1, "oxygen_sat": None, "respiratory_rate": None, "notes": "patient feels warm"}),
    ("full round: BP 122/78, HR 68, temp 36.8, sats 99, RR 15",
     {"bp_systolic": 122, "bp_diastolic": 78, "heart_rate": 68, "temperature": 36.8, "oxygen_sat": 99, "respiratory_rate": 15, "notes": ""}),
], ids=["bp-hr", "temp-only-with-note", "full-round"])
def test_headnurse_records_vitals_via_voice(client, head_nurse, patient_id, auth_headers, monkeypatch, voice_text, extraction):
    mock_groq_json(monkeypatch, extraction)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(head_nurse)).json()[0]
    for field in ("bp_systolic", "bp_diastolic", "heart_rate", "temperature", "oxygen_sat", "respiratory_rate"):
        assert saved[field] == extraction[field]


def test_headnurse_voice_vitals_on_unassigned_patient_succeeds(client, head_nurse, patient_id, auth_headers, monkeypatch):
    """The core assignment-independence check -- a Nurse would get 403 here, HeadNurse must
    always succeed regardless of who (if anyone) is assigned."""
    mock_groq_json(monkeypatch, {"heart_rate": 72})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "heart rate seventy two"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_voice_vitals_extraction_failure_returns_422(client, head_nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, "not valid json output from the model")
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "mumbled vitals"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 422


def test_headnurse_voice_vitals_malformed_field_type_coerced_not_crashed(client, head_nurse, patient_id, auth_headers, monkeypatch):
    # bp_systolic is a numeric string (LLM formatted it with a unit) -- coerces to 130.
    # heart_rate is a list (LLM returned the wrong shape entirely) -- coerces to None, not a crash.
    mock_groq_json(monkeypatch, {"bp_systolic": "130 mmHg", "heart_rate": [70], "temperature": None,
                                  "oxygen_sat": None, "respiratory_rate": None, "notes": ""})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "garbled reading"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(head_nurse)).json()[0]
    assert saved["bp_systolic"] == 130
    assert saved["heart_rate"] is None


# ---------------------------------------------------------------------------
# Voice nursing notes as HeadNurse
# ---------------------------------------------------------------------------

def test_headnurse_creates_nursing_note_via_voice(client, head_nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"subjective": "Patient comfortable", "objective": "Vitals stable",
                                  "assessment": "Improving", "plan": "Continue current care plan"})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": "patient is comfortable, vitals stable, improving"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert "Patient comfortable" in details["nursing_notes"][0]["notes"]
    assert details["nursing_notes"][0]["nurse_email"] == head_nurse.email


def test_headnurse_voice_note_on_unassigned_patient_succeeds(client, head_nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"subjective": "Fine", "objective": "", "assessment": "", "plan": ""})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": "patient fine"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_voice_note_extraction_failure_returns_422(client, head_nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, "[1, 2, 3]")
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": "mumbled note"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 422


def test_headnurse_writes_multiple_voice_notes_across_a_shift(client, head_nurse, patient_id, auth_headers, monkeypatch):
    for i, note in enumerate(["Morning: stable", "Afternoon: improving", "Evening: ready for discharge tomorrow"]):
        mock_groq_json(monkeypatch, {"subjective": note, "objective": "", "assessment": "", "plan": ""})
        resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": note}, headers=auth_headers(head_nurse))
        assert resp.status_code == 200
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert len(details["nursing_notes"]) == 3


# ---------------------------------------------------------------------------
# Nurse-consult (combined) as HeadNurse
# ---------------------------------------------------------------------------

def test_headnurse_runs_full_nurse_consult_via_voice(client, head_nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {
        "vitals": [{"parameter": "BP", "value": "120/80", "unit": "mmHg"}],
        "labs": [{"test": "Hb", "result": "13.0"}],
        "nursing_note": {"subjective": "Stable", "objective": "Alert", "assessment": "Stable", "plan": "Routine care"},
    })
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "full consult dictation"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["vitals"]) == 1
    assert len(data["labs"]) == 1


def test_headnurse_nurse_consult_does_not_persist_anything(client, head_nurse, patient_id, auth_headers, monkeypatch, db_session):
    from app.models import Vital, NursingNote
    mock_groq_json(monkeypatch, {"vitals": [{"parameter": "HR", "value": "80", "unit": "bpm"}], "labs": [],
                                  "nursing_note": {"subjective": "ok", "objective": "", "assessment": "", "plan": ""}})
    client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "HR 80"}, headers=auth_headers(head_nurse))
    assert db_session.query(Vital).count() == 0
    assert db_session.query(NursingNote).count() == 0


def test_headnurse_nurse_consult_on_unassigned_patient_succeeds(client, head_nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "quick check"},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_headnurse_full_voice_consult_then_save_round_trip(client, head_nurse, patient_id, auth_headers, monkeypatch, db_session):
    """The complete Process-then-Save flow as HeadNurse: preview via nurse-consult, then
    persist via the same two calls the frontend issues (structured vitals + nursing note)."""
    from app.models import Vital, NursingNote
    mock_groq_json(monkeypatch, {
        "vitals": [{"parameter": "Heart Rate", "value": "85", "unit": "bpm"}],
        "labs": [], "nursing_note": {"subjective": "Fine", "objective": "", "assessment": "", "plan": ""},
    })
    preview = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "HR 85, patient fine"},
                           headers=auth_headers(head_nurse))
    assert preview.status_code == 200

    save_vital = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 85, "bp_systolic": None,
                                                        "bp_diastolic": None, "temperature": None, "oxygen_sat": None,
                                                        "respiratory_rate": None, "notes": ""}, headers=auth_headers(head_nurse))
    assert save_vital.status_code == 200
    save_note = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "Fine", "objective": "",
                                                          "assessment": "", "plan": ""}, headers=auth_headers(head_nurse))
    assert save_note.status_code == 200

    assert db_session.query(Vital).count() == 1
    assert db_session.query(NursingNote).count() == 1


# ---------------------------------------------------------------------------
# voice-to-vitals preview endpoint as HeadNurse
# ---------------------------------------------------------------------------

def test_headnurse_uses_voice_to_vitals_preview(client, head_nurse, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"bp_systolic": 128, "bp_diastolic": 82})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "BP 128/82"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert resp.json()["bp_systolic"] == 128


def test_headnurse_voice_to_vitals_does_not_require_a_patient(client, head_nurse, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"heart_rate": 90})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "HR 90"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unicode/multilingual voice content as HeadNurse (parity with the Nurse-focused sweep)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("voice_text,note_text", [
    ("मरीज़ को हल्की खांसी है", "मरीज़ को हल्की खांसी है"),
    ("patient theek hai, koi problem nahi", "patient theek hai, koi problem nahi"),
    ("রোগীর অবস্থা স্থিতিশীল", "রোগীর অবস্থা স্থিতিশীল"),
], ids=["hindi", "code-switched", "bengali"])
def test_headnurse_unicode_voice_notes(client, head_nurse, patient_id, auth_headers, monkeypatch, voice_text, note_text):
    mock_groq_json(monkeypatch, {"subjective": note_text, "objective": "", "assessment": "", "plan": ""})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(head_nurse)).json()
    assert note_text in details["nursing_notes"][0]["notes"]


# ---------------------------------------------------------------------------
# Cross-org / malformed-JSON crash resistance specifically as HeadNurse
# ---------------------------------------------------------------------------

def test_headnurse_voice_endpoints_blocked_cross_org(client, head_nurse, make_user, db_session, auth_headers, monkeypatch):
    from app.models import Patient
    other_head = make_user(email="other-head@hn-voice.com", role="HeadNurse")
    patient = Patient(name="Foreign Voice Patient", ward="General", bed="F1",
                       organization_id=other_head.organization_id, created_by=other_head.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    mock_groq_json(monkeypatch, {"heart_rate": 80})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient.id, "voice_text": "HR 80"}, headers=auth_headers(head_nurse))
    assert resp.status_code in (403, 404)


@pytest.mark.parametrize("raw_response", ["[1,2,3]", "true", "not json", ""])
def test_headnurse_voice_vitals_never_crashes_on_any_malformed_response(client, head_nurse, patient_id, auth_headers, monkeypatch, raw_response):
    mock_groq_json(monkeypatch, raw_response)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "mumbled"}, headers=auth_headers(head_nurse))
    assert resp.status_code in (200, 422), f"{raw_response!r}: {resp.status_code} {resp.text}"
