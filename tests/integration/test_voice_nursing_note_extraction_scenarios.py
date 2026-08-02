"""
Large-scenario coverage for the voice-based nursing-note feature: POST /api/nursing-notes with
a `voice_text` field, which asks Groq to structure a SOAP note (subjective/objective/
assessment/plan) from a nurse's spoken narrative. Every case mocks the Groq call and asserts
the endpoint's handling of the result, plus the raw transcript round-trips correctly through
`voice_transcript` (unlike Vital, NursingNote actually stores the raw voice text verbatim).
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@voice-notes.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@voice-notes.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Voice Notes Patient", "ward": "General", "bed": "N1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


def _note(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch):
    mock_groq_json(monkeypatch, extraction)
    return client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": voice_text},
                        headers=auth_headers(nurse))


def _latest_note(client, nurse, patient_id, auth_headers):
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(nurse)).json()
    return details["nursing_notes"][0]


# ---------------------------------------------------------------------------
# Realistic full SOAP dictations
# ---------------------------------------------------------------------------

FULL_SOAP_CASES = [
    ("patient says the headache is better today, alert and oriented, no fever, continue current plan and reassess tomorrow",
     {"subjective": "Headache improved", "objective": "Alert and oriented, afebrile", "assessment": "Improving", "plan": "Continue current plan, reassess tomorrow"}),
    ("patient reports nausea after breakfast, vomited once, abdomen soft non-tender, likely medication side effect, hold oral meds and recheck in 2 hours",
     {"subjective": "Nausea after breakfast, vomited once", "objective": "Abdomen soft, non-tender",
      "assessment": "Likely medication side effect", "plan": "Hold oral meds, recheck in 2 hours"}),
    ("family reports patient more confused since morning, disoriented to time, notify physician immediately and increase monitoring frequency",
     {"subjective": "Family reports increased confusion since morning", "objective": "Disoriented to time",
      "assessment": "Acute confusion, warrants urgent review", "plan": "Notify physician immediately, increase monitoring frequency"}),
    ("post surgical wound looks clean and dry, no discharge, patient denies pain at site, healing well, continue dressing changes daily",
     {"subjective": "Denies pain at incision site", "objective": "Wound clean and dry, no discharge",
      "assessment": "Healing well", "plan": "Continue daily dressing changes"}),
]


@pytest.mark.parametrize("voice_text,extraction", FULL_SOAP_CASES, ids=[f"full-soap-{i}" for i in range(len(FULL_SOAP_CASES))])
def test_full_soap_dictation_saved_correctly(client, nurse, patient_id, auth_headers, monkeypatch, voice_text, extraction):
    resp = _note(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200
    note = _latest_note(client, nurse, patient_id, auth_headers)
    for section, text in extraction.items():
        assert text in note["notes"]
    assert note["voice_transcript"] == voice_text


# ---------------------------------------------------------------------------
# Single-section dictations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("section", ["subjective", "objective", "assessment", "plan"])
def test_single_soap_section_dictation(client, nurse, patient_id, auth_headers, monkeypatch, section):
    extraction = {"subjective": "", "objective": "", "assessment": "", "plan": ""}
    extraction[section] = "Only this section was captured from the dictation"
    resp = _note(client, nurse, patient_id, auth_headers, "brief note", extraction, monkeypatch)
    assert resp.status_code == 200
    note = _latest_note(client, nurse, patient_id, auth_headers)
    assert "Only this section was captured" in note["notes"]


# ---------------------------------------------------------------------------
# Extraction returning wrong types for SOAP fields -- f-string formatting in create_nursing_note
# means these should never crash (unlike the numeric Vital columns), but confirm it.
# ---------------------------------------------------------------------------

MALFORMED_TYPE_CASES = [
    ("subjective_as_list", {"subjective": ["headache", "nausea"], "objective": "", "assessment": "", "plan": ""}),
    ("objective_as_dict", {"subjective": "", "objective": {"bp": "120/80"}, "assessment": "", "plan": ""}),
    ("assessment_as_number", {"subjective": "", "objective": "", "assessment": 42, "plan": ""}),
    ("plan_as_bool", {"subjective": "", "objective": "", "assessment": "", "plan": True}),
    ("all_fields_as_none_explicitly", {"subjective": None, "objective": None, "assessment": None, "plan": None}),
]


@pytest.mark.parametrize("case_id,extraction", MALFORMED_TYPE_CASES, ids=[c[0] for c in MALFORMED_TYPE_CASES])
def test_malformed_soap_field_types_never_crash(client, nurse, patient_id, auth_headers, monkeypatch, case_id, extraction):
    resp = _note(client, nurse, patient_id, auth_headers, "some dictation", extraction, monkeypatch)
    assert resp.status_code in (200, 422), f"{case_id} crashed: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# Malformed-JSON-from-Groq fallback (JSONDecodeError -> OPD-shaped fallback -> all SOAP fields
# blank -> 422 emptiness guard) and valid-JSON-wrong-shape (list/scalar -> same treatment)
# ---------------------------------------------------------------------------

MALFORMED_RESPONSES = [
    "Patient reports headache, appears comfortable, plan to monitor (not JSON)",
    "```\nnot valid json\n```",
    "",
    "null",
    "[1, 2, 3]",
    "true",
    "just the number 42",
]


@pytest.mark.parametrize("raw_response", MALFORMED_RESPONSES, ids=[f"malformed-{i}" for i in range(len(MALFORMED_RESPONSES))])
def test_malformed_groq_response_returns_422_not_500(client, nurse, patient_id, auth_headers, monkeypatch, raw_response):
    mock_groq_json(monkeypatch, raw_response)
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": "mumbled note"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422, f"raw_response={raw_response!r} produced {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Unicode / multilingual dictation, long narrative notes, and raw-transcript round-trip fidelity
# ---------------------------------------------------------------------------

def test_long_narrative_dictation_preserved(client, nurse, patient_id, auth_headers, monkeypatch):
    long_subjective = "Patient described a detailed history of symptoms over the past week. " * 30
    extraction = {"subjective": long_subjective, "objective": "Stable", "assessment": "Chronic condition", "plan": "Continue monitoring"}
    resp = _note(client, nurse, patient_id, auth_headers, "long dictation", extraction, monkeypatch)
    assert resp.status_code == 200
    note = _latest_note(client, nurse, patient_id, auth_headers)
    assert long_subjective in note["notes"]


def test_unicode_hindi_dictation_note_saved(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {"subjective": "मरीज़ को हल्का बुखार है", "objective": "तापमान सामान्य से थोड़ा अधिक",
                  "assessment": "हल्का संक्रमण संभावित", "plan": "निगरानी जारी रखें"}
    resp = _note(client, nurse, patient_id, auth_headers, "हिंदी में नोट", extraction, monkeypatch)
    assert resp.status_code == 200
    note = _latest_note(client, nurse, patient_id, auth_headers)
    assert "मरीज़ को हल्का बुखार है" in note["notes"]


def test_raw_voice_transcript_stored_verbatim_including_unicode(client, nurse, patient_id, auth_headers, monkeypatch):
    voice_text = "patient theek hai, BP normal, कोई दर्द नहीं 👍"
    extraction = {"subjective": "Patient fine, no pain", "objective": "BP normal", "assessment": "Stable", "plan": "Routine care"}
    resp = _note(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200
    note = _latest_note(client, nurse, patient_id, auth_headers)
    assert note["voice_transcript"] == voice_text


@pytest.mark.parametrize("voice_text", [
    "a" * 3000,
    "note with\nmultiple\nlines\nand\ttabs",
    "<script>alert('xss')</script> patient stable",
    "'; DROP TABLE nursing_notes; -- patient stable",
    "🏥 patient stable 🩺 no concerns 💊",
    "     lots of leading and trailing whitespace     ",
], ids=["very-long", "multiline-tabs", "xss-like", "sql-injection-like", "emoji-heavy", "whitespace-padded"])
def test_voice_input_string_variety_never_crashes(client, nurse, patient_id, auth_headers, monkeypatch, voice_text):
    extraction = {"subjective": "Patient stable", "objective": "No concerns", "assessment": "Stable", "plan": "Routine"}
    resp = _note(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200, f"voice_text={voice_text!r} produced {resp.status_code}: {resp.text}"


def test_voice_text_non_string_type_handled_cleanly(client, nurse, patient_id, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"subjective": "", "objective": "", "assessment": "", "plan": ""})
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": [1, 2, 3]},
                        headers=auth_headers(nurse))
    assert resp.status_code in (200, 422), f"non-string voice_text crashed: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# PHI-leakage check specific to the voice nursing-note path (parallel to
# tests/integration/test_phi_leakage.py's OPD-scribe coverage, which doesn't touch this endpoint)
# ---------------------------------------------------------------------------

def test_raw_voice_transcript_never_echoed_in_422_error_response(client, nurse, patient_id, auth_headers, monkeypatch):
    sensitive_voice_text = "patient John Doe SSN 123-45-6789 reports nothing useful"
    mock_groq_json(monkeypatch, "not valid json at all")
    resp = client.post("/api/nursing-notes", json={"patient_id": patient_id, "voice_text": sensitive_voice_text},
                        headers=auth_headers(nurse))
    assert resp.status_code == 422
    assert sensitive_voice_text not in resp.text
    assert "123-45-6789" not in resp.text


# ---------------------------------------------------------------------------
# Multiple notes over a shift -- realistic ward accumulation
# ---------------------------------------------------------------------------

def test_multiple_voice_notes_across_a_shift_all_preserved_in_order(client, nurse, patient_id, auth_headers, monkeypatch):
    dictations = [
        ("morning round, patient stable", {"subjective": "Stable at morning round", "objective": "", "assessment": "", "plan": ""}),
        ("afternoon check, patient napping", {"subjective": "Napping, afternoon check", "objective": "", "assessment": "", "plan": ""}),
        ("evening handoff, patient ate dinner well", {"subjective": "Ate dinner well, evening handoff", "objective": "", "assessment": "", "plan": ""}),
    ]
    for voice_text, extraction in dictations:
        resp = _note(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
        assert resp.status_code == 200
    details = client.get(f"/api/patients/{patient_id}/details", headers=auth_headers(nurse)).json()
    assert len(details["nursing_notes"]) == 3
    assert "evening handoff" in details["nursing_notes"][0]["notes"] or "handoff" in details["nursing_notes"][0]["notes"].lower()
