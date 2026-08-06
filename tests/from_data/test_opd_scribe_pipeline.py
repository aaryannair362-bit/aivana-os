"""
OPD scribe pipeline tests driven by the 12 real consultation transcripts extracted from
./data (see fixtures.py docstring for provenance and the "never assert known_* against a
mocked Groq response" rule -- a mock cannot tell us whether the LLM's real clinical
extraction is accurate, only whether AIVANA's plumbing handles the round trip correctly).

What these tests verify, per case:
  - POST /api/scribe accepts the real, full-length transcript (some 1000+ words, mixed
    Hinglish/English, containing vitals with unicode degree/superscript signs) without
    choking on size or encoding.
  - The mocked "model output" (built from that case's own known_diagnoses/known_medications,
    i.e. ground truth transcribed from the same PDF) flows through to the API response and the
    persisted Consultation row unmangled -- EXCEPT for medications, which real POST /api/scribe
    always runs through drug_matcher.correct_medication_names() before responding (see
    scribe.py), same as a real request would; asserting against the raw fixture string there
    would make this test lie about what the endpoint actually returns. Several of these real
    reference-PDF medication names turned out to be exactly the case drug_matcher.py's
    reseller-prefix/dose-safety fixes were written for (bare "Tab X mg" generics the matcher
    couldn't previously see at all) -- see drug_matcher.py's module docstring.
  - raw_transcript is stored byte-for-byte (PHI-fidelity: a scribe that silently mangles or
    truncates the source transcript is a clinical-safety bug, not just a cosmetic one).
  - The consultation is retrievable only by the user who created it (existing user_id scoping
    in GET /api/consultations/{id} -- see tests/integration/test_multi_tenant_isolation.py for
    the equivalent IPD-side checks).

Traceability: each test is parametrized by CASES[i]["id"], and failure output includes
source_pdf + case_label so a failure can be traced back to the exact PDF case.
"""
import copy
import re

import pytest

from app import drug_matcher
from tests.from_data.fixtures import CASES
from tests.conftest import mock_groq_json


def _mock_result_for(case):
    """Build a plausible structured LLM output from a case's own ground-truth fields."""
    return {
        "chiefComplaint": case["title"],
        "hpi": f"Patient context: {case['patient_context']}",
        "primaryDiagnosis": case["known_diagnoses"][0],
        "differentialDiagnosis": ", ".join(case["known_diagnoses"]),
        "medications": [
            {"drugName": med, "dose": "", "frequency": "", "route": "", "duration": ""}
            for med in case["known_medications"]
        ],
        "advice": "Follow up as advised.",
        "labTests": [],
    }


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@opd-test.com", role="Doctor")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_scribe_pipeline_persists_real_transcript_case(client, doctor, auth_headers, monkeypatch, case):
    mocked_output = _mock_result_for(case)
    mock_groq_json(monkeypatch, mocked_output)

    resp = client.post(
        "/api/scribe",
        json={"transcript": case["transcript"]},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 200, (
        f"scribe endpoint rejected real transcript from {case['source_pdf']} / "
        f"{case['case_label']}: {resp.text}"
    )
    body = resp.json()
    assert body["primaryDiagnosis"] == case["known_diagnoses"][0]
    assert len(body["medications"]) == len(case["known_medications"])
    expected_medications = drug_matcher.correct_medication_names(copy.deepcopy(mocked_output["medications"]))
    assert [m["drugName"] for m in body["medications"]] == [m["drugName"] for m in expected_medications]

    consultations = client.get("/api/consultations", headers=auth_headers(doctor)).json()["consultations"]
    matching = [c for c in consultations if c["primary_diagnosis"] == case["known_diagnoses"][0]]
    assert matching, f"Consultation for {case['id']} was not persisted"
    consultation_id = matching[0]["id"]
    assert re.match(r"^\d{8}-[0-9a-f]{6}$", matching[0]["case_id"]), "case_id format changed"

    detail = client.get(f"/api/consultations/{consultation_id}", headers=auth_headers(doctor)).json()
    assert detail["raw_transcript"] == case["transcript"], (
        f"raw_transcript for {case['source_pdf']} / {case['case_label']} was not stored "
        "byte-for-byte -- possible truncation or encoding mangling of source transcript"
    )
    assert detail["medications"] == expected_medications


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_consultation_not_visible_to_a_different_user(client, doctor, make_user, auth_headers, monkeypatch, case):
    """Privacy: another clinician (even in the same org) must not be able to fetch this
    consultation by id -- GET /api/consultations/{id} scopes by user_id, not just org."""
    mock_groq_json(monkeypatch, _mock_result_for(case))
    client.post("/api/scribe", json={"transcript": case["transcript"]}, headers=auth_headers(doctor))

    consultations = client.get("/api/consultations", headers=auth_headers(doctor)).json()["consultations"]
    consultation_id = consultations[0]["id"]

    other_doctor = make_user(email=f"other-{case['id']}@opd-test.com", role="Doctor",
                              organization_id=doctor.organization_id)
    resp = client.get(f"/api/consultations/{consultation_id}", headers=auth_headers(other_doctor))
    assert resp.status_code == 404


def test_longest_real_transcript_survives_malformed_llm_response(client, doctor, auth_headers, monkeypatch):
    """
    Regression/robustness check using the longest fixture transcript (TB case, tc1-case1-newpatient,
    ~1100 lines / several thousand characters): even against a real-world-sized transcript, a
    malformed (non-JSON) LLM response must still degrade to the safe all-empty-defaults draft
    rather than a 500, per scribe.py's documented fallback behavior.
    """
    case = next(c for c in CASES if c["id"] == "tc1-case1-newpatient")
    mock_groq_json(monkeypatch, "This is not JSON at all { the model rambled instead")

    resp = client.post("/api/scribe", json={"transcript": case["transcript"]}, headers=auth_headers(doctor))
    assert resp.status_code == 200
    body = resp.json()
    assert body["medications"] == []
    assert body["labTests"] == []


def test_all_fixture_transcripts_exceed_minimum_length_guard():
    """Sanity check on the fixture set itself: main.py rejects transcript < 10 chars after
    strip(); every real case must clear that bar with headroom, or the fixture is malformed."""
    for case in CASES:
        assert len(case["transcript"].strip()) > 100, f"{case['id']} transcript suspiciously short"


def test_fixture_ids_are_unique_and_traceable_to_source_pdf():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate fixture id -- traceability broken"
    for case in CASES:
        assert case["source_pdf"] in (
            "Test Cases.pdf", "Test Cases (1).pdf", "Test Cases (2).pdf",
        )
        assert case["case_label"], f"{case['id']} missing case_label for traceability"
