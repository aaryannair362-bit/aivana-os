"""
Large-scenario coverage for POST /api/ipd/nurse-consult -- the combined voice extraction
endpoint (vitals + labs + SOAP note in one dictation) nurses use for a full patient consult.
Since the persistence fix (see CHANGELOG.md), this endpoint is preview-only: it never writes to
the database, so these tests focus on response-shape correctness and crash-resistance across a
wide variety of mocked Groq outputs, rather than DB state.
"""
import copy

import pytest

from tests.conftest import mock_groq_json
from app import lab_test_matcher


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@voice-consult.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@voice-consult.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_id(client, head_nurse, nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "Voice Consult Patient", "ward": "General", "bed": "C1"},
                        headers=auth_headers(head_nurse))
    pid = resp.json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    return pid


def _consult(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch):
    mock_groq_json(monkeypatch, extraction)
    return client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": voice_text},
                        headers=auth_headers(nurse))


# ---------------------------------------------------------------------------
# Full combined dictations: vitals + labs + note all present
# ---------------------------------------------------------------------------

FULL_CONSULT_CASES = [
    (
        "BP 120/80, HR 72, Hb 12.5, WBC 8000, patient reports mild fatigue, stable overall, continue current medications",
        {
            "vitals": [{"parameter": "BP", "value": "120/80", "unit": "mmHg"}, {"parameter": "HR", "value": "72", "unit": "bpm"}],
            "labs": [{"test": "Hb", "result": "12.5"}, {"test": "WBC", "result": "8000"}],
            "nursing_note": {"subjective": "Mild fatigue", "objective": "Stable", "assessment": "Stable overall", "plan": "Continue current medications"},
        },
    ),
    (
        "temperature 39.2 fever, platelets low at 90000, patient looks unwell, monitor closely and consider antipyretics",
        {
            "vitals": [{"parameter": "Temperature", "value": "39.2", "unit": "C"}],
            "labs": [{"test": "Platelets", "result": "90000"}],
            "nursing_note": {"subjective": "Looks unwell", "objective": "Febrile", "assessment": "Fever, thrombocytopenia", "plan": "Monitor closely, consider antipyretics"},
        },
    ),
]


@pytest.mark.parametrize("voice_text,extraction", FULL_CONSULT_CASES, ids=[f"full-consult-{i}" for i in range(len(FULL_CONSULT_CASES))])
def test_full_combined_dictation_returned_for_review(client, nurse, patient_id, auth_headers, monkeypatch, voice_text, extraction):
    resp = _consult(client, nurse, patient_id, auth_headers, voice_text, extraction, monkeypatch)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vitals"] == extraction["vitals"]
    # app/lab_test_matcher.py normalizes each lab entry's "test" name (e.g. "WBC" ->
    # "Total Leucocyte Count") -- pins down that normalization as intended current behavior.
    # deepcopy: correct_lab_test_entries mutates its argument in place.
    assert data["labs"] == lab_test_matcher.correct_lab_test_entries(copy.deepcopy(extraction["labs"]), key="test")
    assert data["nursing_note"] == extraction["nursing_note"]


# ---------------------------------------------------------------------------
# Partial extraction: vitals-only, labs-only, note-only, and completely empty
# ---------------------------------------------------------------------------

def test_vitals_only_extraction(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {"vitals": [{"parameter": "HR", "value": "80", "unit": "bpm"}], "labs": [], "nursing_note": {}}
    resp = _consult(client, nurse, patient_id, auth_headers, "just heart rate eighty", extraction, monkeypatch)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["vitals"]) == 1
    assert data["labs"] == []


def test_labs_only_extraction(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {"vitals": [], "labs": [{"test": "Creatinine", "result": "1.1"}], "nursing_note": {}}
    resp = _consult(client, nurse, patient_id, auth_headers, "creatinine one point one", extraction, monkeypatch)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vitals"] == []
    assert len(data["labs"]) == 1


def test_note_only_extraction(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {"vitals": [], "labs": [], "nursing_note": {"subjective": "Patient anxious about discharge", "objective": "", "assessment": "", "plan": ""}}
    resp = _consult(client, nurse, patient_id, auth_headers, "patient anxious about going home", extraction, monkeypatch)
    assert resp.status_code == 200
    data = resp.json()
    assert data["nursing_note"]["subjective"] == "Patient anxious about discharge"


def test_completely_empty_extraction_returns_empty_shapes_not_error(client, nurse, patient_id, auth_headers, monkeypatch):
    """Preview-only endpoint: unlike record_vital/create_nursing_note, an empty extraction is
    not an error here -- the frontend's own Save-time guard is what stops an empty save."""
    extraction = {"vitals": [], "labs": [], "nursing_note": {}}
    resp = _consult(client, nurse, patient_id, auth_headers, "unintelligible mumbling", extraction, monkeypatch)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vitals"] == []
    assert data["labs"] == []


# ---------------------------------------------------------------------------
# Multiple vitals/labs items -- a nurse dictating several readings and test results in one go
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vitals_count", [1, 2, 3, 5, 8])
def test_multiple_vitals_items_extraction(client, nurse, patient_id, auth_headers, monkeypatch, vitals_count):
    vitals = [{"parameter": f"Param{i}", "value": str(70 + i), "unit": ""} for i in range(vitals_count)]
    extraction = {"vitals": vitals, "labs": [], "nursing_note": {}}
    resp = _consult(client, nurse, patient_id, auth_headers, "many vitals dictated", extraction, monkeypatch)
    assert resp.status_code == 200
    assert len(resp.json()["vitals"]) == vitals_count


@pytest.mark.parametrize("labs_count", [1, 2, 3, 5, 8])
def test_multiple_labs_items_extraction(client, nurse, patient_id, auth_headers, monkeypatch, labs_count):
    labs = [{"test": f"Test{i}", "result": str(i)} for i in range(labs_count)]
    extraction = {"vitals": [], "labs": labs, "nursing_note": {}}
    resp = _consult(client, nurse, patient_id, auth_headers, "many labs dictated", extraction, monkeypatch)
    assert resp.status_code == 200
    assert len(resp.json()["labs"]) == labs_count


# ---------------------------------------------------------------------------
# Malformed sub-structures: vitals/labs items missing expected keys, or the wrong shape
# entirely -- must never crash even though nothing here is persisted.
# ---------------------------------------------------------------------------

MALFORMED_SUBSTRUCTURE_CASES = [
    ("vital_missing_value_key", {"vitals": [{"parameter": "BP"}], "labs": [], "nursing_note": {}}),
    ("vital_missing_parameter_key", {"vitals": [{"value": "120/80"}], "labs": [], "nursing_note": {}}),
    ("lab_missing_result_key", {"vitals": [], "labs": [{"test": "Hb"}], "nursing_note": {}}),
    ("lab_missing_test_key", {"vitals": [], "labs": [{"result": "12.5"}], "nursing_note": {}}),
    ("vitals_is_not_a_list", {"vitals": "BP 120/80", "labs": [], "nursing_note": {}}),
    ("labs_is_not_a_list", {"vitals": [], "labs": "Hb 12.5", "nursing_note": {}}),
    ("nursing_note_is_not_a_dict", {"vitals": [], "labs": [], "nursing_note": "patient stable"}),
    ("nursing_note_missing_entirely", {"vitals": [], "labs": []}),
    ("vitals_missing_entirely", {"labs": [], "nursing_note": {}}),
    ("vital_item_is_a_string_not_dict", {"vitals": ["BP 120/80"], "labs": [], "nursing_note": {}}),
    ("lab_item_is_a_string_not_dict", {"vitals": [], "labs": ["Hb 12.5"], "nursing_note": {}}),
    ("everything_null", {"vitals": None, "labs": None, "nursing_note": None}),
]


@pytest.mark.parametrize("case_id,extraction", MALFORMED_SUBSTRUCTURE_CASES, ids=[c[0] for c in MALFORMED_SUBSTRUCTURE_CASES])
def test_malformed_substructures_never_crash(client, nurse, patient_id, auth_headers, monkeypatch, case_id, extraction):
    resp = _consult(client, nurse, patient_id, auth_headers, "some dictation", extraction, monkeypatch)
    assert resp.status_code == 200, f"{case_id} crashed instead of degrading gracefully: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# Malformed-JSON / wrong-top-level-shape from Groq
# ---------------------------------------------------------------------------

MALFORMED_TOP_LEVEL_RESPONSES = [
    "not valid json at all, just prose",
    "```\nstill not json\n```",
    "",
    "null",
    "[1, 2, 3]",
    "true",
    "\"just a string\"",
]


@pytest.mark.parametrize("raw_response", MALFORMED_TOP_LEVEL_RESPONSES, ids=[f"malformed-{i}" for i in range(len(MALFORMED_TOP_LEVEL_RESPONSES))])
def test_malformed_groq_response_returns_200_with_empty_shapes(client, nurse, patient_id, auth_headers, monkeypatch, raw_response):
    """Unlike record_vital/create_nursing_note (which persist and therefore must 422 on total
    failure), nurse-consult persists nothing -- a failed extraction just comes back empty for
    the nurse to see and retry, so 200 is correct here."""
    mock_groq_json(monkeypatch, raw_response)
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "mumbled consult"},
                        headers=auth_headers(nurse))
    assert resp.status_code == 200, f"raw_response={raw_response!r} produced {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Access control specific to voice content (org isolation / assignment already covered
# elsewhere for non-voice payloads; these confirm the same holds with real voice bodies)
# ---------------------------------------------------------------------------

def test_cross_org_nurse_consult_blocked_regardless_of_voice_content(client, make_user, auth_headers, monkeypatch):
    org_a_head = make_user(email="head.a@voice-consult-org.com", role="HeadNurse")
    org_b_head = make_user(email="head.b@voice-consult-org.com", role="HeadNurse")
    pid = client.post("/api/ipd/patients", json={"name": "Org B Patient", "ward": "General", "bed": "B1"},
                       headers=auth_headers(org_b_head)).json()["id"]
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": pid, "voice_text": "cross org attempt"},
                        headers=auth_headers(org_a_head))
    assert resp.status_code in (403, 404)


def test_unassigned_nurse_blocked_regardless_of_voice_content(client, head_nurse, make_user, patient_id, auth_headers, monkeypatch):
    other_nurse = make_user(email="other@voice-consult.com", role="Nurse", organization_id=head_nurse.organization_id)
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "unassigned attempt"},
                        headers=auth_headers(other_nurse))
    assert resp.status_code == 403


@pytest.mark.parametrize("role", ["NursingStation", "Doctor", "Admin"])
def test_non_nursing_roles_blocked_from_voice_consult(client, head_nurse, make_user, patient_id, auth_headers, monkeypatch, role):
    other_user = make_user(email=f"{role.lower()}@voice-consult.com", role=role, organization_id=head_nurse.organization_id)
    mock_groq_json(monkeypatch, {"vitals": [], "labs": [], "nursing_note": {}})
    resp = client.post("/api/ipd/nurse-consult", json={"patient_id": patient_id, "voice_text": "role test"},
                        headers=auth_headers(other_user))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Unicode / multilingual combined dictation
# ---------------------------------------------------------------------------

def test_unicode_combined_dictation(client, nurse, patient_id, auth_headers, monkeypatch):
    extraction = {
        "vitals": [{"parameter": "BP", "value": "110/70", "unit": "mmHg"}],
        "labs": [],
        "nursing_note": {"subjective": "मरीज़ ठीक महसूस कर रहा है", "objective": "", "assessment": "", "plan": ""},
    }
    resp = _consult(client, nurse, patient_id, auth_headers, "BP एक सौ दस बटा सत्तर, मरीज़ ठीक है", extraction, monkeypatch)
    assert resp.status_code == 200
    assert resp.json()["nursing_note"]["subjective"] == "मरीज़ ठीक महसूस कर रहा है"
