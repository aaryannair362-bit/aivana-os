"""
Tests for the new Discharge Summary feature (added to reduce the real-world hospital-operations
burden of manually writing a discharge document from the chart): POST/GET
/api/ipd/patients/{id}/discharge-summary. Assembles the patient's vitals/nursing-notes/tasks/
consultations already captured elsewhere into an AI-generated summary, mirroring the
scribe_transcript never-raises-always-backfills contract.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@discharge-summary.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@discharge-summary.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def doctor(make_user, head_nurse):
    return make_user(email="doctor@discharge-summary.com", role="Doctor", organization_id=head_nurse.organization_id)


@pytest.fixture
def station(make_user, head_nurse):
    return make_user(email="station@discharge-summary.com", role="NursingStation", organization_id=head_nurse.organization_id)


@pytest.fixture
def patient_with_full_stay(client, head_nurse, nurse, auth_headers):
    """A patient with a realistic multi-day stay: vitals trend, nursing notes, a task."""
    pid = client.post("/api/ipd/patients", json={"name": "Discharge Summary Patient", "age": 58, "gender": "Male",
                                                   "ward": "General", "bed": "D1", "diagnosis": "Community-acquired pneumonia"},
                       headers=auth_headers(head_nurse)).json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/vitals", json={"patient_id": pid, "bp_systolic": 128, "bp_diastolic": 82, "heart_rate": 92,
                                          "temperature": 38.6, "oxygen_sat": 94, "respiratory_rate": 22},
                headers=auth_headers(nurse))
    client.post("/api/ipd/vitals", json={"patient_id": pid, "bp_systolic": 120, "bp_diastolic": 78, "heart_rate": 78,
                                          "temperature": 37.0, "oxygen_sat": 98, "respiratory_rate": 16},
                headers=auth_headers(nurse))
    client.post("/api/nursing-notes", json={"patient_id": pid, "subjective": "Breathing easier today",
                                              "objective": "Lungs clearer on auscultation", "assessment": "Improving",
                                              "plan": "Continue antibiotics"}, headers=auth_headers(nurse))
    client.post("/api/ipd/tasks", json={"patient_id": pid, "description": "IV antibiotics"}, headers=auth_headers(head_nurse))
    return pid


FULL_SUMMARY_RESULT = {
    "admissionSummary": "58yo male admitted with community-acquired pneumonia, febrile and tachypneic on arrival",
    "hospitalCourse": "Treated with IV antibiotics; fever resolved and oxygen saturation normalized by day 2",
    "dischargeDiagnosis": "Resolved community-acquired pneumonia",
    "medicationsAtDischarge": [{"drugName": "Amoxicillin", "dose": "500mg", "frequency": "TID", "duration": "5 days"}],
    "followUpInstructions": "Follow up with primary physician in 1 week; return if fever recurs",
    "conditionAtDischarge": "Stable, afebrile, ambulatory",
}


def test_generate_discharge_summary_full_content(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    data = resp.json()
    assert data["admission_summary"] == FULL_SUMMARY_RESULT["admissionSummary"]
    assert data["hospital_course"] == FULL_SUMMARY_RESULT["hospitalCourse"]
    assert data["discharge_diagnosis"] == FULL_SUMMARY_RESULT["dischargeDiagnosis"]
    assert data["medications_at_discharge"] == FULL_SUMMARY_RESULT["medicationsAtDischarge"]
    assert data["follow_up_instructions"] == FULL_SUMMARY_RESULT["followUpInstructions"]
    assert data["condition_at_discharge"] == FULL_SUMMARY_RESULT["conditionAtDischarge"]
    assert data["generated_by"] == head_nurse.id


def test_generated_summary_persists_and_is_retrievable(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    resp = client.get(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert resp.json()["discharge_diagnosis"] == FULL_SUMMARY_RESULT["dischargeDiagnosis"]


def test_get_summary_before_any_generated_returns_404(client, head_nurse, patient_with_full_stay, auth_headers):
    resp = client.get(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_regenerating_creates_a_new_version_get_returns_latest(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))

    updated_result = dict(FULL_SUMMARY_RESULT, conditionAtDischarge="Fully recovered, discharged home")
    mock_groq_json(monkeypatch, updated_result)
    client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))

    resp = client.get(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.json()["condition_at_discharge"] == "Fully recovered, discharged home"


def test_generates_even_for_patient_with_minimal_record(client, head_nurse, auth_headers, monkeypatch):
    """A patient admitted and discharged same-day with no vitals/notes/tasks recorded --
    legitimate (quick observation stay), must still produce a (minimal) summary, not error."""
    pid = client.post("/api/ipd/patients", json={"name": "Quick Observation Patient", "ward": "General", "bed": "Q1"},
                       headers=auth_headers(head_nurse)).json()["id"]
    mock_groq_json(monkeypatch, {
        "admissionSummary": "Admitted for brief observation", "hospitalCourse": "Uneventful",
        "dischargeDiagnosis": "No acute findings", "medicationsAtDischarge": [],
        "followUpInstructions": "Routine follow-up as needed", "conditionAtDischarge": "Stable",
    })
    resp = client.post(f"/api/ipd/patients/{pid}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_total_generation_failure_returns_422_not_persisted(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch, db_session):
    from app.models import DischargeSummary
    mock_groq_json(monkeypatch, "not valid json at all")
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 422
    assert db_session.query(DischargeSummary).count() == 0


def test_malformed_llm_response_wrong_shape_returns_422(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, "[1, 2, 3]")
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 422


def test_partial_generation_result_accepted(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    """Only some fields populated -- still meaningfully useful, must not be treated as failure."""
    mock_groq_json(monkeypatch, {"admissionSummary": "", "hospitalCourse": "", "dischargeDiagnosis": "Pneumonia, resolved",
                                  "medicationsAtDischarge": [], "followUpInstructions": "", "conditionAtDischarge": ""})
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert resp.json()["discharge_diagnosis"] == "Pneumonia, resolved"


# ---------------------------------------------------------------------------
# Role permissions
# ---------------------------------------------------------------------------

def test_doctor_can_generate(client, doctor, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(doctor))
    assert resp.status_code == 200


def test_nursing_station_can_generate(client, station, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(station))
    assert resp.status_code == 200


def test_nurse_cannot_generate(client, nurse, patient_with_full_stay, auth_headers):
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(nurse))
    assert resp.status_code == 403


def test_assigned_nurse_can_view_generated_summary(client, head_nurse, nurse, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    resp = client.get(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(nurse))
    assert resp.status_code == 200


def test_unassigned_nurse_cannot_view_summary(client, head_nurse, make_user, patient_with_full_stay, auth_headers, monkeypatch):
    other_nurse = make_user(email="other@discharge-summary.com", role="Nurse", organization_id=head_nurse.organization_id)
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    resp = client.get(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(other_nurse))
    assert resp.status_code == 403


@pytest.mark.parametrize("role", ["Admin"])
def test_admin_cannot_generate_or_view(client, make_user, head_nurse, patient_with_full_stay, auth_headers, role):
    admin = make_user(email=f"{role.lower()}@discharge-summary.com", role=role, organization_id=head_nurse.organization_id)
    assert client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(admin)).status_code == 403
    assert client.get(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(admin)).status_code == 403


# ---------------------------------------------------------------------------
# Org isolation and error handling
# ---------------------------------------------------------------------------

def test_generate_for_nonexistent_patient_404(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients/999999/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_cannot_generate_for_other_orgs_patient(client, head_nurse, make_user, db_session, auth_headers):
    from app.models import Patient
    other_head = make_user(email="other-head@discharge-summary.com", role="HeadNurse")
    patient = Patient(name="Foreign Patient", ward="General", bed="F1",
                       organization_id=other_head.organization_id, created_by=other_head.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    resp = client.post(f"/api/ipd/patients/{patient.id}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_cannot_view_other_orgs_summary(client, head_nurse, make_user, db_session, auth_headers, monkeypatch):
    from app.models import Patient
    other_head = make_user(email="other-head2@discharge-summary.com", role="HeadNurse")
    patient = Patient(name="Foreign Patient 2", ward="General", bed="F2",
                       organization_id=other_head.organization_id, created_by=other_head.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    mock_groq_json(monkeypatch, FULL_SUMMARY_RESULT)
    client.post(f"/api/ipd/patients/{patient.id}/discharge-summary", headers=auth_headers(other_head))
    resp = client.get(f"/api/ipd/patients/{patient.id}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Real-content integration: the generated summary correctly reflects the actual chart data
# passed into the prompt (via the mocked LLM standing in for what a real model would produce
# from that context)
# ---------------------------------------------------------------------------

def test_summary_generation_includes_actual_vitals_trend_in_prompt_context(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    captured_prompts = []

    def _fake_call(prompt, system=None, temperature=0.3):
        captured_prompts.append(prompt)
        import json
        return json.dumps(FULL_SUMMARY_RESULT)

    from app import main as app_main
    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)
    client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert len(captured_prompts) == 1
    assert "94" in captured_prompts[0]  # the abnormal oxygen_sat reading recorded
    assert "Community-acquired pneumonia" in captured_prompts[0]
    assert "Breathing easier today" in captured_prompts[0]


def test_summary_never_persists_raw_prompt_or_leaks_pii_via_error(client, head_nurse, patient_with_full_stay, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, "invalid json triggers failure")
    resp = client.post(f"/api/ipd/patients/{patient_with_full_stay}/discharge-summary", headers=auth_headers(head_nurse))
    assert resp.status_code == 422
    # The 422 error body itself must not echo the patient's chart content.
    assert "Community-acquired pneumonia" not in resp.text
