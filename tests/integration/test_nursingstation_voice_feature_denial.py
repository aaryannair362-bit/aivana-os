"""
Confirms NursingStation's denial from every voice-capable endpoint holds regardless of the
actual voice_text content -- complements test_nursingstation_denial_consistency.py's structural
JSON-shape focus with transcript-content variety (unicode, very long, injection-shaped),
proving the role check fires before the transcript is ever inspected or sent to Groq.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def station(make_user):
    return make_user(email="station@ns-voice-denial.com", role="NursingStation")


@pytest.fixture
def patient_id(client, station, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Voice Denial Patient", "ward": "General", "bed": "V1"},
                        headers=auth_headers(station))
    return resp.json()["id"]


VOICE_TEXT_VARIETY = [
    ("short", "BP 120/80"),
    ("long", "patient stable. " * 100),
    ("unicode_hindi", "मरीज़ स्थिर है"),
    ("unicode_arabic", "المريض مستقر"),
    ("emoji", "🩺 patient stable 💉"),
    ("xss_shaped", "<script>alert(1)</script>"),
    ("sql_injection_shaped", "'; DROP TABLE vitals; --"),
    ("empty_string", ""),
    ("whitespace_only", "   "),
]


@pytest.mark.parametrize("case_id,voice_text", VOICE_TEXT_VARIETY, ids=[c[0] for c in VOICE_TEXT_VARIETY])
def test_station_denied_from_voice_vitals_regardless_of_transcript_content(client, station, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    """Groq is never even called -- if it were, the autouse _no_live_groq_calls fixture would
    raise RuntimeError instead of letting the test reach a clean 403."""
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(station))
    assert resp.status_code == 403, f"{case_id}: expected 403, got {resp.status_code}"


@pytest.mark.parametrize("case_id,voice_text", VOICE_TEXT_VARIETY, ids=[c[0] for c in VOICE_TEXT_VARIETY])
def test_station_denied_from_voice_nursing_notes_regardless_of_transcript_content(client, station, patient_id, auth_headers, case_id, voice_text):
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(station))
    assert resp.status_code == 403, f"{case_id}: expected 403, got {resp.status_code}"


@pytest.mark.parametrize("case_id,voice_text", VOICE_TEXT_VARIETY, ids=[c[0] for c in VOICE_TEXT_VARIETY])
def test_station_denied_from_nurse_consult_regardless_of_transcript_content(client, station, patient_id, auth_headers, case_id, voice_text):
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(station))
    if case_id == "empty_string":
        # nurse_consult validates `not voice_text` (required-field check) BEFORE its role
        # check, unlike its siblings -- an empty string is falsy, so this one case legitimately
        # 400s before ever reaching the 403. Pre-existing, already-tested ordering.
        assert resp.status_code == 400
    else:
        assert resp.status_code == 403, f"{case_id}: expected 403, got {resp.status_code}"


@pytest.mark.parametrize("case_id,voice_text", VOICE_TEXT_VARIETY, ids=[c[0] for c in VOICE_TEXT_VARIETY])
def test_station_denied_from_voice_to_vitals_regardless_of_transcript_content(client, station, auth_headers, case_id, voice_text):
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": voice_text}, headers=auth_headers(station))
    assert resp.status_code == 403, f"{case_id}: expected 403, got {resp.status_code}"


def test_groq_never_actually_invoked_for_a_denied_station_voice_request(client, station, patient_id, auth_headers, monkeypatch):
    """Explicit proof (not just absence of a crash): patch _call_groq_api to raise if called at
    all, confirming the 403 truly happens before any LLM call is attempted."""
    from app import main as app_main

    def _must_not_be_called(*a, **k):
        raise AssertionError("Groq must not be called for a role-denied request")

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _must_not_be_called)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "BP 120/80"}, headers=auth_headers(station))
    assert resp.status_code == 403
