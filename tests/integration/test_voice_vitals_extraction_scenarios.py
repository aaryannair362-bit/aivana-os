"""
Large-scenario coverage for the voice-based vitals-recording feature nurses use every day:
POST /api/ipd/vitals with a `voice_text` field, and its standalone-preview sibling
POST /api/ipd/voice-to-vitals. Every case here mocks scribe._call_groq_api (per this repo's
no-live-LLM-calls policy) to return a specific extraction result, then asserts the endpoint
handles that result correctly -- including the type-coercion fix (see CHANGELOG.md) that stops
a malformed LLM response (wrong types, e.g. a list where a number is expected) from crashing
the database insert outright.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@voice-vitals.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@voice-vitals.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Voice Vitals Patient", "ward": "General", "bed": "V1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


def _record(client, nurse, patient_id, auth_headers, voice_text, mocked_extraction, monkeypatch):
    mock_groq_json(monkeypatch, mocked_extraction)
    return client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": voice_text},
                        headers=auth_headers(nurse))


# ---------------------------------------------------------------------------
# Realistic full-consult dictations: every field present, matching how a nurse would actually
# speak a full vitals round.
# ---------------------------------------------------------------------------

FULL_DICTATIONS = [
    ("BP one twenty over eighty, heart rate seventy two, temp thirty seven, sats ninety eight, resp rate sixteen",
     {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": 72, "temperature": 37.0, "oxygen_sat": 98, "respiratory_rate": 16, "notes": ""}),
    ("Blood pressure 140 over 90, pulse 88, temperature 38.2, oxygen 95 percent, breathing rate 20",
     {"bp_systolic": 140, "bp_diastolic": 90, "heart_rate": 88, "temperature": 38.2, "oxygen_sat": 95, "respiratory_rate": 20, "notes": ""}),
    ("patient stable, BP 110/70, HR 65, afebrile at 36.5, SpO2 99, RR 14, resting comfortably",
     {"bp_systolic": 110, "bp_diastolic": 70, "heart_rate": 65, "temperature": 36.5, "oxygen_sat": 99, "respiratory_rate": 14, "notes": "resting comfortably"}),
    ("post-op check, BP 118/76, HR 80, temp 37.8 slightly elevated, sats 96, RR 18, mild pain at incision site",
     {"bp_systolic": 118, "bp_diastolic": 76, "heart_rate": 80, "temperature": 37.8, "oxygen_sat": 96, "respiratory_rate": 18, "notes": "mild pain at incision site"}),
    ("ICU round, BP 92/58 on pressors, HR 110, temp 39.1, sats 92 on 4L O2, RR 24, patient drowsy",
     {"bp_systolic": 92, "bp_diastolic": 58, "heart_rate": 110, "temperature": 39.1, "oxygen_sat": 92, "respiratory_rate": 24, "notes": "on pressors, 4L O2, patient drowsy"}),
]


@pytest.mark.parametrize("voice_text,extraction", FULL_DICTATIONS, ids=[f"full-dictation-{i}" for i in range(len(FULL_DICTATIONS))])
def test_full_dictation_saves_all_fields_correctly(client, nurse, patient_id, auth_headers, monkeypatch, voice_text, extraction):
    resp = _record(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()[0]
    for field in ("bp_systolic", "bp_diastolic", "heart_rate", "temperature", "oxygen_sat", "respiratory_rate"):
        assert saved[field] == extraction[field]


# ---------------------------------------------------------------------------
# Single-vital dictations -- a nurse quickly checking just one parameter must not be blocked or
# have unrelated fields incorrectly populated.
# ---------------------------------------------------------------------------

SINGLE_FIELD_CASES = [
    ("temperature", 37.6, "temp check, thirty seven point six"),
    ("heart_rate", 68, "pulse is sixty eight"),
    ("oxygen_sat", 94, "sats reading ninety four"),
    ("respiratory_rate", 22, "breathing twenty two per minute"),
    ("bp_systolic", 130, "systolic one thirty"),
]


@pytest.mark.parametrize("field,value,voice_text", SINGLE_FIELD_CASES, ids=[c[0] for c in SINGLE_FIELD_CASES])
def test_single_field_dictation_only_populates_that_field(client, nurse, patient_id, auth_headers, monkeypatch, field, value, voice_text):
    extraction = {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None, "temperature": None,
                  "oxygen_sat": None, "respiratory_rate": None, "notes": ""}
    extraction[field] = value
    resp = _record(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()[0]
    assert saved[field] == value
    other_fields = [f for f in ("bp_systolic", "bp_diastolic", "heart_rate", "temperature", "oxygen_sat", "respiratory_rate") if f != field]
    for f in other_fields:
        assert saved[f] is None


# ---------------------------------------------------------------------------
# Type-coercion robustness: the LLM's JSON output isn't schema-enforced. These must never crash
# (see CHANGELOG.md's type-coercion fix) and must degrade sensibly.
# ---------------------------------------------------------------------------

MALFORMED_TYPE_CASES = [
    ("bp_systolic_as_string_number", {"bp_systolic": "120", "bp_diastolic": None, "heart_rate": None, "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"bp_systolic": 120}),
    ("heart_rate_as_string_with_unit", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": "72 bpm", "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"heart_rate": 72}),
    ("temperature_as_string_decimal", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None, "temperature": "37.5 C", "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"temperature": 37.5}),
    ("bp_systolic_as_list_becomes_null", {"bp_systolic": [120, 80], "bp_diastolic": None, "heart_rate": 70, "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"bp_systolic": None, "heart_rate": 70}),
    ("heart_rate_as_non_numeric_word_becomes_null", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": "seventy", "temperature": 37.0, "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"heart_rate": None, "temperature": 37.0}),
    ("oxygen_sat_as_dict_becomes_null", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None, "temperature": None, "oxygen_sat": {"value": 98}, "respiratory_rate": None, "notes": "sats look fine"}, {"oxygen_sat": None}),
    ("respiratory_rate_as_bool_becomes_null", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": 80, "temperature": None, "oxygen_sat": None, "respiratory_rate": True, "notes": ""}, {"respiratory_rate": None, "heart_rate": 80}),
    ("temperature_as_float_string_with_noise", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None, "temperature": "around 38.4 degrees", "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"temperature": 38.4}),
    ("negative_string_parsed_correctly", {"bp_systolic": None, "bp_diastolic": None, "heart_rate": "-5", "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""}, {"heart_rate": -5}),
]


@pytest.mark.parametrize("case_id,extraction,expected", MALFORMED_TYPE_CASES, ids=[c[0] for c in MALFORMED_TYPE_CASES])
def test_malformed_llm_field_types_never_crash(client, nurse, patient_id, auth_headers, monkeypatch, case_id, extraction, expected):
    resp = _record(client, nurse, patient_id, auth_headers, "some voice note", extraction, monkeypatch)
    assert resp.status_code == 200, f"{case_id} crashed instead of degrading gracefully: {resp.status_code} {resp.text}"
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()[0]
    for field, value in expected.items():
        assert saved[field] == value, f"{case_id}: expected {field}={value}, got {saved[field]}"


def test_notes_field_as_non_string_is_stringified_not_crashed(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None, "temperature": None,
                  "oxygen_sat": None, "respiratory_rate": None, "notes": ["patient", "restless"]}
    resp = _record(client, nurse, patient_id, auth_headers, "patient restless", extraction, monkeypatch)
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()[0]
    assert "restless" in saved["notes"]


def test_all_fields_malformed_and_no_recoverable_notes_returns_422(client, nurse, patient_id, auth_headers, monkeypatch):
    """Every field unparseable AND no notes -- must be treated the same as a total extraction
    failure (422), not silently saved as an all-null row."""
    extraction = {"bp_systolic": [1, 2], "bp_diastolic": "high", "heart_rate": {}, "temperature": "warm",
                  "oxygen_sat": "good", "respiratory_rate": "normal", "notes": ""}
    resp = _record(client, nurse, patient_id, auth_headers, "vibes only, no numbers", extraction, monkeypatch)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Extraction returning unexpected extra keys must be ignored, not crash.
# ---------------------------------------------------------------------------

def test_extraction_with_unexpected_extra_keys_ignored(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": 70, "temperature": 37.0,
                  "oxygen_sat": 98, "respiratory_rate": 16, "notes": "",
                  "patient_name": "should be ignored", "confidence": 0.87, "extra_nested": {"a": 1}}
    resp = _record(client, nurse, patient_id, auth_headers, "full vitals", extraction, monkeypatch)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unicode / multilingual voice content -- realistic for an Indian hospital where nurses may
# code-switch between Hindi and English, or dictate in Hindi entirely.
# ---------------------------------------------------------------------------

UNICODE_NOTES_CASES = [
    "मरीज़ स्थिर है, दर्द नहीं है",  # "patient is stable, no pain" in Hindi
    "BP normal hai, patient theek lag raha hai",  # code-switched Hindi-English
    "রোগী স্থিতিশীল",  # Bengali: "patient is stable"
    "நோயாளி நிலையானவர்",  # Tamil: "patient is stable"
    "patient comfortable 😊, vitals stable",
]


@pytest.mark.parametrize("notes_text", UNICODE_NOTES_CASES, ids=[f"unicode-{i}" for i in range(len(UNICODE_NOTES_CASES))])
def test_unicode_and_code_switched_notes_preserved(client, nurse, patient_id, auth_headers, monkeypatch, notes_text):
    extraction = {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": None, "temperature": None,
                  "oxygen_sat": None, "respiratory_rate": None, "notes": notes_text}
    resp = _record(client, nurse, patient_id, auth_headers, notes_text, extraction, monkeypatch)
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()[0]
    assert saved["notes"] == notes_text


# ---------------------------------------------------------------------------
# voice_text input string variety (the raw transcript sent, independent of what comes back)
# ---------------------------------------------------------------------------

VOICE_INPUT_VARIETY = [
    "a" * 3000,  # very long single dictation
    "BP 120/80\nHR 72\nTemp 37.0",  # multi-line
    "   BP 120 over 80, with lots of   extra   whitespace   ",
    "BP one-twenty-over-eighty",
    "<script>alert(1)</script> BP 120/80",  # XSS-like content in a voice transcript
    "'; DROP TABLE vitals; --  BP 120/80",  # SQL-injection-like content
    "🩺 BP 120/80 💉",
]


@pytest.mark.parametrize("voice_text", VOICE_INPUT_VARIETY, ids=[f"input-variety-{i}" for i in range(len(VOICE_INPUT_VARIETY))])
def test_voice_input_string_variety_never_crashes(client, nurse, patient_id, auth_headers, monkeypatch, voice_text):
    extraction = {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": None, "temperature": None,
                  "oxygen_sat": None, "respiratory_rate": None, "notes": ""}
    resp = _record(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200, f"voice_text={voice_text!r} produced {resp.status_code}: {resp.text}"


def test_voice_text_non_string_type_handled_cleanly(client, nurse, patient_id, auth_headers, monkeypatch):
    """A client bug (or malformed request) sending voice_text as a number/list instead of a
    string must not crash the endpoint. voice_text is only truthy-checked (`if voice_text:`),
    then f-string-interpolated into the prompt -- both operations are safe for any type."""
    mock_groq_json(monkeypatch, {"bp_systolic": None, "bp_diastolic": None, "heart_rate": None,
                                  "temperature": None, "oxygen_sat": None, "respiratory_rate": None, "notes": ""})
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": 12345},
                        headers=auth_headers(nurse))
    assert resp.status_code in (200, 422), f"non-string voice_text crashed: {resp.status_code} {resp.text}"


def test_empty_string_voice_text_falls_back_to_manual_path(client, nurse, patient_id, auth_headers):
    """An empty string is falsy, so `if voice_text:` is False -- this should behave exactly
    like a manual submission with no voice_text key at all (i.e. no LLM call is made; the raw
    request body's fields, if any, are used directly)."""
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "", "heart_rate": 77},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200
    saved = client.get(f"/api/ipd/vitals/{patient_id}", headers=auth_headers(nurse)).json()[0]
    assert saved["heart_rate"] == 77


# ---------------------------------------------------------------------------
# Malformed-JSON-from-Groq fallback path (JSONDecodeError -> _fallback_extract, OPD-shaped)
# ---------------------------------------------------------------------------

MALFORMED_JSON_RESPONSES = [
    "The patient's vitals were BP 120/80, HR 72 (not valid JSON, just prose)",
    "```\nnot json either\n```",
    "{broken json missing quotes: 120}",
    "",
    "null",
    "[1, 2, 3]",  # valid JSON but wrong shape (a list, not a dict)
]


@pytest.mark.parametrize("raw_response", MALFORMED_JSON_RESPONSES, ids=[f"malformed-json-{i}" for i in range(len(MALFORMED_JSON_RESPONSES))])
def test_malformed_groq_json_response_returns_422_not_500(client, nurse, patient_id, auth_headers, monkeypatch, raw_response):
    mock_groq_json(monkeypatch, raw_response)
    resp = client.post("/api/ipd/vitals", json={"patient_id": patient_id, "voice_text": "mumbled vitals"},
                        headers=auth_headers(nurse))
    assert resp.status_code in (422, 200), f"raw_response={raw_response!r} produced {resp.status_code}: {resp.text}"
