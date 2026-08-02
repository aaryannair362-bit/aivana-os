"""
Multi-visit diagnostic workup scenarios: cases where a diagnosis isn't finalized in a single
consultation, but emerges across several visits/tests -- a very common real-world pattern
(e.g. a vague presenting complaint, several lab tests ordered, a follow-up visit that finally
confirms the diagnosis). Modeled as a sequence of OPD consultations for the same doctor (and,
where relevant, linked IPD admission) with an evolving diagnosis across visits.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@diagnostic-workup.com", role="Doctor")


@pytest.fixture
def head_nurse(make_user, doctor):
    return make_user(email="head@diagnostic-workup.com", role="HeadNurse", organization_id=doctor.organization_id)


WORKUP_JOURNEYS = [
    ("anemia_workup", [
        ("Patient complains of fatigue and pale appearance for 2 weeks, no other symptoms yet.",
         {"chiefComplaint": "Fatigue and pallor", "primaryDiagnosis": "Anemia, etiology pending workup",
          "labTests": ["CBC", "Peripheral smear", "Iron studies"]}),
        ("Follow-up: CBC shows microcytic hypochromic anemia, iron studies pending, patient reports heavy menstrual periods.",
         {"chiefComplaint": "Follow-up for anemia workup, heavy menstrual bleeding noted", "primaryDiagnosis": "Iron deficiency anemia, likely secondary to menorrhagia",
          "labTests": ["Serum ferritin", "Pelvic ultrasound"]}),
        ("Final visit: ferritin confirms iron deficiency, ultrasound shows uterine fibroid explaining the bleeding.",
         {"chiefComplaint": "Reviewing final workup results", "primaryDiagnosis": "Iron deficiency anemia secondary to uterine fibroid-related menorrhagia",
          "labTests": []}),
    ]),
    ("fever_of_unknown_origin", [
        ("Patient with fever for 10 days, no clear source, extensive first-line workup normal so far.",
         {"chiefComplaint": "Fever of 10 days duration, no localizing symptoms", "primaryDiagnosis": "Pyrexia of unknown origin, first-line workup unremarkable",
          "labTests": ["Blood culture", "Widal test", "Malaria antigen", "Chest X-ray"]}),
        ("Follow-up: blood culture still pending, patient now reports joint pains, considering autoimmune workup.",
         {"chiefComplaint": "Persistent fever with new joint pains", "primaryDiagnosis": "Pyrexia of unknown origin, considering autoimmune etiology",
          "labTests": ["ANA", "RA factor", "ESR", "CRP"]}),
        ("Third visit: ANA strongly positive, rheumatology referral made, diagnosis of likely SLE being finalized.",
         {"chiefComplaint": "Reviewing autoimmune workup results", "primaryDiagnosis": "Suspected Systemic Lupus Erythematosus, referred to rheumatology",
          "labTests": ["Anti-dsDNA", "Complement levels"]}),
    ]),
    ("chest_pain_cardiac_workup", [
        ("Patient with intermittent chest discomfort on exertion for 3 weeks, ECG at rest is normal.",
         {"chiefComplaint": "Exertional chest discomfort, 3 weeks", "primaryDiagnosis": "Chest pain, cardiac etiology to be ruled out, resting ECG normal",
          "labTests": ["Treadmill test", "Lipid profile", "Troponin"]}),
        ("Follow-up: treadmill test positive for inducible ischemia, referred for angiography.",
         {"chiefComplaint": "Reviewing positive stress test result", "primaryDiagnosis": "Inducible myocardial ischemia on stress testing",
          "labTests": ["Coronary angiography"]}),
        ("Final visit: angiography shows 70% stenosis of LAD, planned for angioplasty.",
         {"chiefComplaint": "Reviewing angiography results", "primaryDiagnosis": "Significant LAD stenosis (70%), coronary artery disease confirmed",
          "labTests": []}),
    ]),
    ("abdominal_pain_workup", [
        ("Patient with recurrent right upper quadrant pain after fatty meals for a month.",
         {"chiefComplaint": "Recurrent postprandial right upper quadrant pain", "primaryDiagnosis": "Suspected biliary colic, workup pending",
          "labTests": ["Abdominal ultrasound", "Liver function tests"]}),
        ("Follow-up: ultrasound confirms multiple gallstones, liver function normal, surgery being planned.",
         {"chiefComplaint": "Reviewing ultrasound results showing gallstones", "primaryDiagnosis": "Symptomatic cholelithiasis",
          "labTests": ["Pre-operative workup"]}),
    ]),
    ("weight_loss_workup", [
        ("Patient with unintentional 8kg weight loss over 3 months, no clear cause identified yet.",
         {"chiefComplaint": "Unintentional weight loss, 8kg over 3 months", "primaryDiagnosis": "Weight loss, etiology under investigation",
          "labTests": ["CBC", "TSH", "HbA1c", "Chest X-ray", "Abdominal ultrasound"]}),
        ("Follow-up: TSH markedly elevated (hyperthyroid range), other tests unremarkable, likely explains the weight loss.",
         {"chiefComplaint": "Reviewing thyroid function results", "primaryDiagnosis": "Hyperthyroidism, likely Graves' disease",
          "labTests": ["Free T4", "TSH receptor antibodies", "Thyroid scan"]}),
    ]),
]


@pytest.mark.parametrize("journey_id,visits", WORKUP_JOURNEYS, ids=[j[0] for j in WORKUP_JOURNEYS])
def test_multi_visit_workup_all_visits_recorded_for_same_patient(client, doctor, auth_headers, monkeypatch, journey_id, visits):
    patient_id = 1000 + hash(journey_id) % 5000  # a stable synthetic IPD-independent patient reference for OPD linkage
    for transcript, extraction in visits:
        full_extraction = {"chiefComplaint": "", "hpi": "", "primaryDiagnosis": "", "differentialDiagnosis": "",
                            "medications": [], "advice": "", "labTests": [], **extraction}
        mock_groq_json(monkeypatch, full_extraction)
        resp = client.post("/api/scribe", json={"transcript": transcript, "patient_id": patient_id}, headers=auth_headers(doctor))
        assert resp.status_code == 200, f"{journey_id}: {resp.status_code} {resp.text}"

    consultations = client.get("/api/consultations", headers=auth_headers(doctor)).json()["consultations"]
    matching = [c for c in consultations if c["patient_id"] == patient_id]
    assert len(matching) == len(visits), f"{journey_id}: expected {len(visits)} linked visits, found {len(matching)}"


@pytest.mark.parametrize("journey_id,visits", WORKUP_JOURNEYS, ids=[j[0] for j in WORKUP_JOURNEYS])
def test_multi_visit_workup_diagnosis_evolves_across_visits(client, doctor, auth_headers, monkeypatch, journey_id, visits):
    patient_id = 2000 + hash(journey_id) % 5000
    diagnoses_seen = []
    for transcript, extraction in visits:
        full_extraction = {"chiefComplaint": "", "hpi": "", "primaryDiagnosis": "", "differentialDiagnosis": "",
                            "medications": [], "advice": "", "labTests": [], **extraction}
        mock_groq_json(monkeypatch, full_extraction)
        resp = client.post("/api/scribe", json={"transcript": transcript, "patient_id": patient_id}, headers=auth_headers(doctor))
        diagnoses_seen.append(resp.json()["primaryDiagnosis"])

    # The final visit's diagnosis should differ from (and be more specific than) the first.
    assert diagnoses_seen[0] != diagnoses_seen[-1], f"{journey_id}: diagnosis should refine across visits"
    assert diagnoses_seen[-1] == visits[-1][1]["primaryDiagnosis"]


@pytest.mark.parametrize("journey_id,visits", WORKUP_JOURNEYS, ids=[j[0] for j in WORKUP_JOURNEYS])
def test_multi_visit_workup_lab_tests_narrow_down_across_visits(client, doctor, auth_headers, monkeypatch, journey_id, visits):
    """Later visits in a real workup typically order fewer, more targeted tests than the
    initial broad screen -- confirm the recorded lab test lists reflect that narrowing."""
    patient_id = 3000 + hash(journey_id) % 5000
    lab_counts = []
    for transcript, extraction in visits:
        full_extraction = {"chiefComplaint": "", "hpi": "", "primaryDiagnosis": "", "differentialDiagnosis": "",
                            "medications": [], "advice": "", "labTests": [], **extraction}
        mock_groq_json(monkeypatch, full_extraction)
        resp = client.post("/api/scribe", json={"transcript": transcript, "patient_id": patient_id}, headers=auth_headers(doctor))
        lab_counts.append(len(resp.json()["labTests"]))
    assert lab_counts[0] >= lab_counts[-1], f"{journey_id}: expected lab test breadth to narrow (or stay flat) across the workup"


# ---------------------------------------------------------------------------
# IPD-linked diagnostic workup: an admitted patient whose diagnosis firms up as vitals/labs/
# nursing observations accumulate over the stay, culminating in a discharge summary that
# reflects the full trajectory.
# ---------------------------------------------------------------------------

def test_ipd_diagnostic_workup_culminates_in_accurate_discharge_summary(client, doctor, head_nurse, make_user, auth_headers, monkeypatch):
    nurse = make_user(email="nurse@diagnostic-workup.com", role="Nurse", organization_id=doctor.organization_id)
    hn = auth_headers(head_nurse)
    pid = client.post("/api/ipd/patients", json={"name": "Workup Patient", "ward": "General",
                                                   "diagnosis": "Fever, etiology under evaluation"}, headers=hn).json()["id"]
    client.post("/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurse.id}, headers=hn)

    # Day 1: high fever, tachycardia -- concerning.
    client.post("/api/ipd/vitals", json={"patient_id": pid, "temperature": 39.5, "heart_rate": 118}, headers=auth_headers(nurse))
    client.post("/api/nursing-notes", json={"patient_id": pid, "subjective": "High fever, appears unwell",
                                              "objective": "Temp 39.5, HR 118", "assessment": "Febrile illness under workup",
                                              "plan": "Blood cultures sent, awaiting results"}, headers=auth_headers(nurse))
    # Day 2: improving after culture-directed antibiotics.
    client.post("/api/ipd/vitals", json={"patient_id": pid, "temperature": 37.8, "heart_rate": 92}, headers=auth_headers(nurse))
    client.post("/api/nursing-notes", json={"patient_id": pid, "subjective": "Fever reducing, feels better",
                                              "objective": "Temp 37.8, HR 92", "assessment": "Responding to targeted antibiotics",
                                              "plan": "Continue current antibiotics"}, headers=auth_headers(nurse))
    # Day 3: afebrile, ready for discharge.
    client.post("/api/ipd/vitals", json={"patient_id": pid, "temperature": 36.9, "heart_rate": 76}, headers=auth_headers(nurse))
    client.put(f"/api/patients/{pid}", json={"diagnosis": "Bacteremia, culture-confirmed, treated"}, headers=hn)

    mock_groq_json(monkeypatch, {
        "admissionSummary": "Admitted with high fever and tachycardia of unclear origin",
        "hospitalCourse": "Blood cultures grew organism sensitive to targeted antibiotics; fever resolved over 3 days with improving vitals",
        "dischargeDiagnosis": "Bacteremia, culture-confirmed and treated",
        "medicationsAtDischarge": [{"drugName": "Oral antibiotics", "dose": "as per sensitivity", "frequency": "BD", "duration": "5 more days"}],
        "followUpInstructions": "Complete oral antibiotic course, follow up in 1 week",
        "conditionAtDischarge": "Afebrile and stable",
    })
    summary_resp = client.post(f"/api/ipd/patients/{pid}/discharge-summary", headers=hn)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert "Bacteremia" in summary["discharge_diagnosis"]
    assert summary["condition_at_discharge"] == "Afebrile and stable"
