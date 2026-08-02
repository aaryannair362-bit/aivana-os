"""
Raw voice_text input robustness driven specifically by HeadNurse, across the three persisting
voice endpoints (record_vital, create_nursing_note, nurse-consult) -- parallel to
test_voice_input_robustness.py (which used a Nurse fixture), confirming the same input-handling
guarantees hold for HeadNurse and on patients with no nurse assignment at all.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@hn-voice-robust.com", role="HeadNurse")


@pytest.fixture
def patient_id(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "HN Robustness Patient", "ward": "General", "bed": "R1"},
                        headers=auth_headers(head_nurse))
    return resp.json()["id"]


INPUT_VARIETY = [
    ("very_short", "BP 120/80"),
    ("very_long", "patient stable, no new complaints. " * 150),
    ("unicode_hindi", "मरीज़ स्थिर है, कोई नई शिकायत नहीं"),
    ("unicode_arabic_rtl", "المريض مستقر، لا شكاوى جديدة"),
    ("emoji_heavy", "🏥 BP 120/80 💉 patient stable ✅"),
    ("code_switched", "patient ekdum theek hai, BP normal, no issues"),
    ("control_characters", "BP 120/80\x00\x01 stable"),
    ("nested_quotes", 'nurse said "patient is fine" per chart notes "BP 120/80"'),
    ("sql_injection_shaped", "'; DROP TABLE patients; -- patient stable"),
    ("xss_shaped", "<script>alert('xss')</script> patient stable"),
    ("only_whitespace_padded", "     BP 120/80     "),
    ("multiline", "BP 120/80\nHR 72\nTemp 37.0"),
    ("repeated_spam", "stable " * 100),
    ("numbers_only", "120 80 72 37 98 16"),
    ("mixed_devanagari_numerals", "BP १२०/८० normal"),
]


@pytest.mark.parametrize("case_id,voice_text", INPUT_VARIETY, ids=[c[0] for c in INPUT_VARIETY])
def test_headnurse_voice_vitals_input_variety_never_crashes(client, head_nurse, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    mock_groq_json(monkeypatch, {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": None,
                                  "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"


@pytest.mark.parametrize("case_id,voice_text", INPUT_VARIETY, ids=[c[0] for c in INPUT_VARIETY])
def test_headnurse_voice_notes_input_variety_never_crashes(client, head_nurse, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    mock_groq_json(monkeypatch, {"subjective": "Stable", "objective": "", "assessment": "", "plan": ""})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"


@pytest.mark.parametrize("case_id,voice_text", INPUT_VARIETY, ids=[c[0] for c in INPUT_VARIETY])
def test_headnurse_nurse_consult_input_variety_never_crashes(client, head_nurse, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {"subjective": "ok", "objective": "", "assessment": "", "plan": ""}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"


@pytest.mark.parametrize("raw_response", ["[1,2,3]", "true", "not json at all", "", "null"])
def test_headnurse_voice_vitals_malformed_groq_response_never_500(client, head_nurse, patient_id, auth_headers, monkeypatch, raw_response):
    mock_groq_json(monkeypatch, raw_response)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "mumbled"}, headers=auth_headers(head_nurse))
    assert resp.status_code in (200, 422), f"{raw_response!r}: {resp.status_code} {resp.text}"


def test_headnurse_pii_in_voice_transcript_never_leaks_into_error_response(client, head_nurse, patient_id, auth_headers, monkeypatch):
    sensitive = "patient Ramesh Kumar, Aadhaar 1234 5678 9012, phone 9876543210"
    mock_groq_json(monkeypatch, "invalid json response")
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": sensitive}, headers=auth_headers(head_nurse))
    assert resp.status_code == 422
    assert "1234 5678 9012" not in resp.text
    assert "9876543210" not in resp.text
