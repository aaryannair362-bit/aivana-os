"""
Boundary and malformed-input tests for POST /api/scribe (main.py:315-354).

The minimum-length gate is `not transcript or len(transcript.strip()) < 10` -- these tests
pin down the exact boundary and probe what happens when a client sends a type the endpoint
doesn't expect (a healthcare intake form is exactly the kind of client that sometimes sends
malformed JSON).
"""
import pytest


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@scribe-edge.com", role="Doctor")


def test_missing_transcript_field_rejected(client, doctor, auth_headers):
    resp = client.post("/api/scribe", json={}, headers=auth_headers(doctor))
    assert resp.status_code == 400


def test_transcript_exactly_9_chars_after_strip_rejected(client, doctor, auth_headers):
    resp = client.post("/api/scribe", json={"transcript": "123456789"}, headers=auth_headers(doctor))
    assert resp.status_code == 400
    assert len("123456789") == 9


def test_transcript_exactly_10_chars_after_strip_accepted(client, doctor, auth_headers, monkeypatch):
    from tests.conftest import mock_groq_json
    mock_groq_json(monkeypatch, {"chiefComplaint": "test"})
    resp = client.post("/api/scribe", json={"transcript": "1234567890"}, headers=auth_headers(doctor))
    assert len("1234567890") == 10
    assert resp.status_code == 200


def test_whitespace_padded_short_transcript_rejected_by_stripped_length(client, doctor, auth_headers):
    """" a " (single real char plus padding) strips to length 1 -- must not be counted as 9 raw chars."""
    resp = client.post("/api/scribe", json={"transcript": "   a   b  "}, headers=auth_headers(doctor))
    assert resp.status_code == 400


def test_transcript_all_whitespace_rejected(client, doctor, auth_headers):
    resp = client.post("/api/scribe", json={"transcript": "                     "}, headers=auth_headers(doctor))
    assert resp.status_code == 400


def test_empty_string_transcript_rejected(client, doctor, auth_headers):
    resp = client.post("/api/scribe", json={"transcript": ""}, headers=auth_headers(doctor))
    assert resp.status_code == 400


def test_null_transcript_rejected(client, doctor, auth_headers):
    resp = client.post("/api/scribe", json={"transcript": None}, headers=auth_headers(doctor))
    assert resp.status_code == 400


def test_non_string_transcript_returns_clean_error_not_raw_500(client, doctor, auth_headers):
    """
    A JSON number/array/object in the transcript field is a malformed request, not a server
    fault -- document/pin the actual status code so a future change is noticed either way.
    """
    resp = client.post("/api/scribe", json={"transcript": 1234567890123}, headers=auth_headers(doctor))
    assert resp.status_code in (400, 422), (
        f"non-string transcript produced {resp.status_code}, expected a clean client error"
    )


def test_no_request_body_at_all_returns_client_error_not_crash(client, doctor, auth_headers):
    resp = client.post(
        "/api/scribe",
        data="not json at all {{{",
        headers={**auth_headers(doctor), "Content-Type": "application/json"},
    )
    assert resp.status_code < 500, f"malformed JSON body crashed the endpoint with {resp.status_code}"
