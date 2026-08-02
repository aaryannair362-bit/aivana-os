"""
Raw voice_text input robustness, swept across all three voice-capable endpoints nurses use
(record_vital, create_nursing_note, nurse-consult). These focus on the transcript STRING itself
-- length, script/language, control characters, injection-shaped content -- independent of what
the (mocked) LLM extracts from it, complementing the extraction-result-focused scenario files.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@voice-robustness.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@voice-robustness.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Robustness Patient", "ward": "General", "bed": "R1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


INPUT_VARIETY = [
    ("very_short_valid", "BP 120/80"),
    ("exactly_ten_chars", "BP is fine"),
    ("very_long_5000_chars", "patient stable, no complaints. " * 160),
    ("control_characters", "BP 120/80\x00\x01\x02 HR 72"),
    ("zero_width_characters", "BP​ 120/80‌ HR‍ 72"),
    ("rtl_arabic", "ضغط الدم طبيعي، المريض مستقر"),  # "blood pressure normal, patient stable" (Arabic)
    ("rtl_urdu", "مریض مستحکم ہے، بلڈ پریشر نارمل"),  # Urdu
    ("mixed_scripts_hindi_english_numbers", "BP १२० /८० normal hai, patient theek hai"),
    ("repeated_word_spam", "stable " * 200),
    ("numbers_only", "120 80 72 37 98 16"),
    ("contains_literal_null_word", "patient said null, nothing else, BP 120/80"),
    ("contains_literal_undefined_word", "reading was undefined initially, then BP 120/80"),
    ("contains_the_word_none", "patient has none of the usual symptoms, BP 120/80"),
    ("multiple_patients_mentioned_confusion", "for bed 3 BP is 120/80, wait I mean bed 5, sorry, patient in this bed is fine"),
    ("nested_quotes", 'patient said "I feel fine" and BP is "120/80" according to the monitor'),
    ("backslashes_and_escapes", "BP 120\\80, patient stable\\nfine"),
    ("percent_signs", "sats 98% on room air, BP 120/80"),
    ("currency_and_special_symbols", "cost aside, BP 120/80, patient €$¥ stable #1 priority"),
    ("only_punctuation", "...,,,!!!???---"),
    ("single_repeated_character", "a" * 500),
    ("tab_and_newline_heavy", "BP\t120/80\nHR\t72\n\n\nTemp\t37.0"),
]


@pytest.mark.parametrize("case_id,voice_text", INPUT_VARIETY, ids=[c[0] for c in INPUT_VARIETY])
def test_record_vital_input_variety_never_crashes(client, nurse, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    mock_groq_json(monkeypatch, {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": None,
                                  "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(nurse))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"


@pytest.mark.parametrize("case_id,voice_text", INPUT_VARIETY, ids=[c[0] for c in INPUT_VARIETY])
def test_create_nursing_note_input_variety_never_crashes(client, nurse, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    mock_groq_json(monkeypatch, {"subjective": "Stable", "objective": "", "assessment": "", "plan": ""})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(nurse))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"


@pytest.mark.parametrize("case_id,voice_text", INPUT_VARIETY, ids=[c[0] for c in INPUT_VARIETY])
def test_nurse_consult_input_variety_never_crashes(client, nurse, patient_id, auth_headers, monkeypatch, case_id, voice_text):
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {"subjective": "ok", "objective": "", "assessment": "", "plan": ""}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(nurse))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# The transcript minimum-length semantics differ per endpoint -- OPD's /api/scribe enforces a
# 10-char minimum (tests/integration/test_scribe_input_edge_cases.py); the IPD voice endpoints
# have no such minimum, only a truthiness check. Document that explicitly.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("voice_text", ["a", "1", "hi", "ok"])
def test_ipd_voice_endpoints_have_no_minimum_length_unlike_opd_scribe(client, nurse, patient_id, auth_headers, monkeypatch, voice_text):
    mock_groq_json(monkeypatch, {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None,
                                  "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": "brief note"})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": voice_text}, headers=auth_headers(nurse))
    assert resp.status_code == 200, (
        f"voice_text={voice_text!r} (very short) was rejected -- IPD voice endpoints were "
        f"expected to have no minimum-length gate, only OPD's /api/scribe does: {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Whitespace-only voice_text is falsy-after-strip in intent but NOT falsy in Python's bare
# truthiness check (`if voice_text:` treats " " as truthy) -- document current behavior.
# ---------------------------------------------------------------------------

def test_whitespace_only_voice_text_is_still_treated_as_present(client, nurse, patient_id, auth_headers, monkeypatch):
    """`if voice_text:` is a raw truthiness check with no .strip() -- a single space is
    truthy, so this DOES trigger the LLM extraction path (unlike an empty string)."""
    call_log = []

    def _fake(prompt, system=None, temperature=0.3):
        call_log.append(prompt)
        import json
        return json.dumps({"bp_systolic": None, "bp_diastolic": None, "heart_rate": None,
                            "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": "captured"})

    from app import main as app_main
    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "   "}, headers=auth_headers(nurse))
    assert resp.status_code == 200
    assert len(call_log) == 1, "whitespace-only voice_text should still be truthy and trigger extraction"


# ---------------------------------------------------------------------------
# PHI safety: raw voice content must never leak into an error response body, across all three
# persisting endpoints when extraction fails.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint,body_extra", [
    ("/api/ipd/vitals", {}),
    ("/api/nursing-notes", {}),
])
def test_sensitive_voice_content_never_echoed_on_extraction_failure(client, nurse, patient_id, auth_headers, monkeypatch, endpoint, body_extra):
    sensitive = "patient Jane Doe, phone 9876543210, reports confidential family history of illness"
    mock_groq_json(monkeypatch, "totally invalid json response")
    resp = client.post(endpoint, json={"patient_id": patient_id, "voice_text": sensitive, **body_extra}, headers=auth_headers(nurse))
    assert resp.status_code == 422
    assert sensitive not in resp.text
    assert "9876543210" not in resp.text


def test_sensitive_voice_content_not_echoed_by_nurse_consult_on_bad_json(client, nurse, patient_id, auth_headers, monkeypatch):
    sensitive = "patient Jane Doe, phone 9876543210"
    mock_groq_json(monkeypatch, "totally invalid json response")
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": sensitive}, headers=auth_headers(nurse))
    assert resp.status_code == 200  # preview-only, degrades to empty rather than erroring
    assert "9876543210" not in resp.text
