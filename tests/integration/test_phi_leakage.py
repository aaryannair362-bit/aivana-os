"""
PHI/secret leakage checks: error responses returned to the client must never echo raw
transcript content or plaintext passwords back, even when something fails downstream.
ARCHITECTURE_NOTES.md already flags that scribe.py prints full transcripts to stdout on
every call (an operational logging concern, not fixed here since operators may rely on those
prints for debugging) -- these tests are narrower: they check the HTTP response body itself,
which is what would show up in browser devtools, API gateways, or a support ticket screenshot.
"""
import pytest


SECRET_TRANSCRIPT_MARKER = "PATIENT_SECRET_MARKER_Neha_Patil_HIV_status_XYZ123"


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@phi-test.com", role="Doctor")


def test_scribe_500_error_does_not_echo_transcript_content(client, doctor, auth_headers, monkeypatch):
    """
    If the Groq call raises unexpectedly (not caught by scribe.py's own safety net -- e.g. a
    bug in a future refactor), main.py's except-block returns f"Error: {str(e)}". This must
    not, even incidentally, include the raw transcript text in the response body.
    """
    import app.main as app_main

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated downstream failure")

    monkeypatch.setattr(app_main.scribe, "scribe_transcript", _boom)

    transcript = f"Doctor: {SECRET_TRANSCRIPT_MARKER} patient reports symptoms in detail here today"
    resp = client.post("/api/scribe", json={"transcript": transcript}, headers=auth_headers(doctor))
    assert resp.status_code == 500
    assert SECRET_TRANSCRIPT_MARKER not in resp.text


def test_scribe_400_validation_error_does_not_echo_transcript(client, doctor, auth_headers):
    resp = client.post("/api/scribe", json={"transcript": "short"}, headers=auth_headers(doctor))
    assert resp.status_code == 400
    assert "short" not in resp.text.lower() or resp.json()["detail"] == "Transcript too short"


def test_login_failure_response_never_contains_submitted_password(client, make_user):
    secret_password = "Sup3rSecret!Passw0rd#Marker"
    make_user(email="phi-login@example.com", password=secret_password)
    resp = client.post("/api/auth/login", json={
        "email": "phi-login@example.com", "password": "WrongOne123!",
    })
    assert secret_password not in resp.text


def test_password_reset_response_never_echoes_new_password(client, make_user, auth_headers):
    admin = make_user(email="phi-admin@example.com", role="Admin")
    new_password = "Br4nd#NewMarkerPw9"
    resp = client.patch(
        f"/api/auth/users/{admin.id}/password",
        json={"new_password": new_password},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert new_password not in resp.text


def test_register_weak_password_error_does_not_echo_the_password_itself(client):
    weak_password = "weakpw123markerXYZ"
    resp = client.post("/api/auth/register", json={
        "email": "weakpw@example.com", "password": weak_password,
    })
    assert resp.status_code == 400
    assert weak_password not in resp.text
