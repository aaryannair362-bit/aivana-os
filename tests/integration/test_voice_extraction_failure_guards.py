"""
Regression tests for the "silent empty save" fix on POST /api/ipd/vitals and
POST /api/nursing-notes.

Before this fix, a totally failed LLM extraction (malformed JSON from Groq, or any other
_generate_json failure) silently produced a Vital/NursingNote with every field null/blank,
saved with a plain 200 "success" response -- a nurse would believe the vital or note was
captured when nothing usable was. Both endpoints now return 422 when extraction (voice) or
submission (manual) yields nothing at all, while still accepting genuinely partial data (a
nurse who only mentions one vital, or only fills in one SOAP section) unchanged.
"""
import pytest

from app import main as app_main
from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@voice-guard.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@voice-guard.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Voice Guard Patient", "ward": "General", "bed": "V1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


# ---------------------------------------------------------------------------
# POST /api/ipd/vitals
# ---------------------------------------------------------------------------

def test_voice_vital_extraction_total_failure_returns_422(client, nurse, patient_id, auth_headers, monkeypatch):
    """Malformed JSON from Groq falls back to scribe.py's OPD-shaped fallback dict, which has
    none of the vital-sign keys -- every field ends up None. Must be rejected, not saved blank."""
    mock_groq_json(monkeypatch, "The patient seems fine, nothing specific to report really")
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "um, the patient, uh, seems okay I guess"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_voice_vital_extraction_generic_exception_returns_422(client, nurse, patient_id, auth_headers, monkeypatch):
    """A generic (non-JSONDecodeError) failure in _generate_json returns {} -- also must 422."""
    def _raise(*a, **k):
        raise ValueError("boom")
    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _raise)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "irrelevant"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_voice_vital_extraction_partial_success_is_saved(client, nurse, patient_id, auth_headers, monkeypatch, db_session):
    """A nurse who only mentions one vital must not be penalized -- partial data still saves."""
    from app.models import Vital
    mock_groq_json(monkeypatch, {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None,
                                  "temperature": 37.8, "oxygen_sat": None, "respiratory_rate": None, "notes": ""})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "temperature is thirty seven point eight"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    saved = db_session.query(Vital).filter(Vital.patient_id == patient_id).first()
    assert saved.temperature == 37.8


def test_voice_vital_extraction_notes_only_is_saved(client, nurse, patient_id, auth_headers, monkeypatch):
    """No numeric vitals extracted, but a meaningful notes string was -- e.g. 'patient refused
    vitals check'. That's real clinical information and must not be discarded as a failure."""
    mock_groq_json(monkeypatch, {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None,
                                  "temperature": None, "oxygen_sat": None, "respiratory_rate": None,
                                  "notes": "Patient refused vitals check, will retry in 1 hour"})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "patient refused vitals check"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200


def test_manual_vital_entry_totally_empty_rejected(client, nurse, patient_id, auth_headers):
    """Same guard applies to the manual (non-voice) path: a POST with only patient_id and
    nothing else is a client no-op, not a valid vital record."""
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id}, headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_manual_vital_entry_with_one_field_accepted(client, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "heart_rate": 82}, headers=auth_headers(nurse))
    assert resp.status_code == 200


def test_manual_vital_entry_notes_only_accepted(client, nurse, patient_id, auth_headers):
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "notes": "Patient sleeping, vitals deferred"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200


def test_manual_vital_entry_zero_values_are_not_treated_as_empty(client, nurse, patient_id, auth_headers, db_session):
    """0 is a legitimate (if alarming) reading, not the same as "not provided" -- must not be
    swept up by the emptiness guard (which checks `is None`, not falsiness)."""
    from app.models import Vital
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "oxygen_sat": 0}, headers=auth_headers(nurse))
    assert resp.status_code == 200
    saved = db_session.query(Vital).filter(Vital.patient_id == patient_id).first()
    assert saved.oxygen_sat == 0


# ---------------------------------------------------------------------------
# POST /api/nursing-notes
# ---------------------------------------------------------------------------

def test_voice_nursing_note_total_failure_returns_422(client, nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, "not json, just rambling text with no structure")
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": "the patient talked for a while"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_voice_nursing_note_partial_extraction_is_saved(client, nurse, patient_id, auth_headers, monkeypatch, db_session):
    from app.models import NursingNote
    mock_groq_json(monkeypatch, {"subjective": "Reports mild headache", "objective": "", "assessment": "", "plan": ""})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": "patient says mild headache"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    saved = db_session.query(NursingNote).filter(NursingNote.patient_id == patient_id).first()
    assert "Reports mild headache" in saved.notes


def test_manual_nursing_note_totally_empty_rejected(client, nurse, patient_id, auth_headers):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "", "objective": "",
                                                     "assessment": "", "plan": ""},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_manual_nursing_note_missing_all_soap_fields_rejected(client, nurse, patient_id, auth_headers):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id}, headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_manual_nursing_note_whitespace_only_rejected(client, nurse, patient_id, auth_headers):
    """Whitespace-only sections must not slip past the emptiness guard."""
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "   ",
                                                     "objective": "\n\t", "assessment": "", "plan": ""},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422


def test_manual_nursing_note_one_section_filled_accepted(client, nurse, patient_id, auth_headers):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "subjective": "",
                                                     "objective": "Vitals stable", "assessment": "", "plan": ""},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200


@pytest.mark.parametrize("field", ["subjective", "objective", "assessment", "plan"])
def test_manual_nursing_note_each_single_field_alone_is_sufficient(client, nurse, patient_id, auth_headers, field):
    body = {"patient_id": patient_id, "subjective": "", "objective": "", "assessment": "", "plan": ""}
    body[field] = "Some content here"
    resp = client.post("/api/nursing-notes", json=body, headers=auth_headers(nurse))
    assert resp.status_code == 200
