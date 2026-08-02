"""
Regression tests: POST /api/scribe used to hardcode patient_name="Patient" and never set
patient_age/patient_gender at all, even when patient_id resolved to a real IPD Patient row
with that data already on file (unlike the IPD-side create_ipd_round, which has always copied
age/gender from the Patient row onto the Consultation it creates). This meant the OPD
"Prepare Rx Sheet" print view could never show a real patient name or age/sex -- it fell back
to the dropdown's raw option text and a hardcoded "N/A" respectively. Fixed in main.py's
scribe_transcript to mirror create_ipd_round's existing pattern.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@scribe-linkage.com", role="Doctor")


@pytest.fixture
def linked_patient(doctor, db_session):
    from app.models import Patient

    patient = Patient(
        name="John Doe", age=45, gender="Male", ward="General", bed="G1",
        diagnosis="Acute Gastroenteritis", organization_id=doctor.organization_id,
        created_by=doctor.id,
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient


def test_scribe_with_linked_patient_returns_real_name_age_gender(client, doctor, linked_patient, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"chiefComplaint": "Fever and loose stools"})
    resp = client.post(
        "/api/scribe",
        json={"transcript": "Patient presents with fever and loose stools.", "patient_id": linked_patient.id},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_name"] == "John Doe"
    assert data["patient_age"] == "45"
    assert data["patient_gender"] == "Male"


def test_scribe_without_patient_id_still_falls_back_to_placeholder(client, doctor, auth_headers, monkeypatch):
    """Walk-in consultations with no patient_id keep the pre-existing placeholder behavior."""
    mock_groq_json(monkeypatch, {"chiefComplaint": "Headache"})
    resp = client.post(
        "/api/scribe",
        json={"transcript": "Patient complains of headache since yesterday."},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_name"] == "Patient"
    assert data["patient_age"] == ""
    assert data["patient_gender"] == ""


def test_scribe_with_patient_missing_age_returns_empty_string_not_none_or_crash(client, doctor, db_session, auth_headers, monkeypatch):
    from app.models import Patient

    patient = Patient(
        name="Jane Roe", age=None, gender="Female", ward="General", bed="G2",
        organization_id=doctor.organization_id, created_by=doctor.id,
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    mock_groq_json(monkeypatch, {"chiefComplaint": "Cough"})
    resp = client.post(
        "/api/scribe",
        json={"transcript": "Patient complains of persistent cough.", "patient_id": patient.id},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_name"] == "Jane Roe"
    assert data["patient_age"] == ""
    assert data["patient_gender"] == "Female"
