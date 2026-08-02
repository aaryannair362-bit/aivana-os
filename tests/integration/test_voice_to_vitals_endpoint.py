"""
Coverage for POST /api/ipd/voice-to-vitals -- a standalone, patient-agnostic voice extraction
preview endpoint (no persistence, no patient_id at all -- just voice_text in, extracted JSON
out). Unlike its siblings, this endpoint previously had NO role check whatsoever (any
authenticated Admin/Doctor/NursingStation could call it); fixed this pass to match
record_vital/nurse_consult's Nurse/HeadNurse restriction. See CHANGELOG.md.
"""
import pytest

from tests.conftest import mock_groq_json


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@voice-to-vitals.com", role="HeadNurse")


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@voice-to-vitals.com", role="Nurse", organization_id=head_nurse.organization_id)


def test_nurse_can_use_voice_to_vitals(client, nurse, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": 72,
                                  "temperature": 37.0, "oxygen_sat": 98, "respiratory_rate": 16, "notes": ""})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "BP 120/80, HR 72"}, headers=auth_headers(nurse))
    assert resp.status_code == 200
    assert resp.json()["bp_systolic"] == 120


def test_head_nurse_can_use_voice_to_vitals(client, head_nurse, auth_headers, monkeypatch):
    mock_groq_json(monkeypatch, {"heart_rate": 80})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "HR 80"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


@pytest.mark.parametrize("role", ["NursingStation", "Doctor", "Admin"])
def test_other_roles_now_blocked_from_voice_to_vitals(client, head_nurse, make_user, auth_headers, monkeypatch, role):
    """Regression test for the role-check fix -- previously ANY authenticated role could call
    this Groq-backed extraction endpoint with no restriction at all."""
    user = make_user(email=f"{role.lower()}@voice-to-vitals.com", role=role, organization_id=head_nurse.organization_id)
    mock_groq_json(monkeypatch, {"heart_rate": 80})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "HR 80"}, headers=auth_headers(user))
    assert resp.status_code == 403


def test_unauthenticated_request_rejected(client):
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "HR 80"})
    assert resp.status_code in (401, 403)


def test_missing_voice_text_rejected(client, nurse, auth_headers):
    resp = client.post("/api/ipd/voice-to-vitals", json={}, headers=auth_headers(nurse))
    assert resp.status_code == 400


def test_empty_string_voice_text_rejected(client, nurse, auth_headers):
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": ""}, headers=auth_headers(nurse))
    assert resp.status_code == 400


def test_no_patient_id_required_at_all(client, nurse, auth_headers, monkeypatch):
    """This endpoint is intentionally patient-agnostic -- a quick scratch-pad preview, not tied
    to any admission record."""
    mock_groq_json(monkeypatch, {"heart_rate": 90})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "HR 90", "patient_id": None}, headers=auth_headers(nurse))
    assert resp.status_code == 200


def test_returns_raw_extraction_unmodified(client, nurse, auth_headers, monkeypatch):
    """Unlike record_vital, this endpoint does NOT type-coerce or validate the extraction --
    it's a passthrough preview. Documents current behavior."""
    mock_groq_json(monkeypatch, {"bp_systolic": "one twenty", "heart_rate": 72, "notes": "extra text"})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "some note"}, headers=auth_headers(nurse))
    assert resp.status_code == 200
    assert resp.json()["bp_systolic"] == "one twenty"


@pytest.mark.parametrize("raw_response", [
    "not valid json",
    "[1, 2, 3]",
    "true",
    "",
    "null",
], ids=["invalid-json", "list-shape", "bool-shape", "empty", "null-literal"])
def test_malformed_groq_response_never_crashes(client, nurse, auth_headers, monkeypatch, raw_response):
    mock_groq_json(monkeypatch, raw_response)
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": "mumbled"}, headers=auth_headers(nurse))
    assert resp.status_code == 200, f"raw_response={raw_response!r} produced {resp.status_code}: {resp.text}"
    assert isinstance(resp.json(), dict)


def test_does_not_persist_anything_to_database(client, nurse, auth_headers, monkeypatch, db_session):
    from app.models import Vital
    mock_groq_json(monkeypatch, {"bp_systolic": 130, "bp_diastolic": 85, "heart_rate": 90})
    client.post("/api/ipd/voice-to-vitals", json={"voice_text": "BP 130/85, HR 90"}, headers=auth_headers(nurse))
    assert db_session.query(Vital).count() == 0


@pytest.mark.parametrize("voice_text", [
    "a" * 2000,
    "मरीज़ का बीपी एक तीस बटा पचासी है",
    "🩺 BP 130/85 💉",
    "<script>alert(1)</script> BP 130/85",
], ids=["very-long", "hindi", "emoji", "xss-like"])
def test_voice_input_variety_never_crashes(client, nurse, auth_headers, monkeypatch, voice_text):
    mock_groq_json(monkeypatch, {"bp_systolic": 130, "bp_diastolic": 85})
    resp = client.post("/api/ipd/voice-to-vitals", json={"voice_text": voice_text}, headers=auth_headers(nurse))
    assert resp.status_code == 200
