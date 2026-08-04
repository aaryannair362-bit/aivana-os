"""
POST /api/transcribe-audio -- server-side speech-to-text backing all 4 voice-input flows
(replaces the browser's SpeechRecognition). Stateless (no DB/patient/org involvement), so
these tests focus on auth, upload validation, and PHI-safe error handling -- the actual
Groq call is mocked via scribe.transcribe_audio (see tests/unit/test_scribe_audio_transcription.py
for the Groq-call-shape tests), following the same mock_groq_json-style convention
test_voice_input_robustness.py uses for the JSON-based voice endpoints.
"""
import pytest

from app import main as app_main


def _mock_transcribe(monkeypatch, text=None, raise_exc=None):
    def _fake(audio_bytes, content_type, filename):
        if raise_exc is not None:
            raise raise_exc
        return text

    monkeypatch.setattr(app_main.scribe, "transcribe_audio", _fake)


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@transcribe-audio.com", role="Doctor")


def test_requires_authentication(client):
    resp = client.post("/api/transcribe-audio", files={"audio": ("r.webm", b"fake-audio", "audio/webm")})
    assert resp.status_code in (401, 403)


def test_returns_transcript_on_success(client, doctor, auth_headers, monkeypatch):
    _mock_transcribe(monkeypatch, text="Patient has acidity for five days, prescribe Pantop 40mg tablet OD")
    resp = client.post(
        "/api/transcribe-audio",
        files={"audio": ("r.webm", b"fake-audio-bytes", "audio/webm")},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 200
    assert resp.json() == {"transcript": "Patient has acidity for five days, prescribe Pantop 40mg tablet OD"}


def test_empty_audio_rejected(client, doctor, auth_headers, monkeypatch):
    _mock_transcribe(monkeypatch, text="should never be reached")
    resp = client.post(
        "/api/transcribe-audio",
        files={"audio": ("r.webm", b"", "audio/webm")},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 400


def test_oversized_audio_rejected(client, doctor, auth_headers, monkeypatch):
    monkeypatch.setattr(app_main, "MAX_AUDIO_UPLOAD_BYTES", 10)
    _mock_transcribe(monkeypatch, text="should never be reached")
    resp = client.post(
        "/api/transcribe-audio",
        files={"audio": ("r.webm", b"x" * 100, "audio/webm")},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 413


def test_groq_failure_returns_generic_error_not_exception_detail(client, doctor, auth_headers, monkeypatch):
    """Same rule /api/scribe follows: a Groq-side error message can echo request/PHI content
    back, so the client must only ever see a generic message, never str(exception)."""
    _mock_transcribe(monkeypatch, raise_exc=RuntimeError("upstream said: patient John Doe has HIV"))
    resp = client.post(
        "/api/transcribe-audio",
        files={"audio": ("r.webm", b"fake-audio-bytes", "audio/webm")},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 502
    assert "John Doe" not in resp.text
    assert "HIV" not in resp.text


def test_missing_groq_api_key_returns_generic_error(client, doctor, auth_headers, monkeypatch):
    _mock_transcribe(monkeypatch, raise_exc=ValueError("Groq API key not configured. Set GROQ_API_KEY in environment."))
    resp = client.post(
        "/api/transcribe-audio",
        files={"audio": ("r.webm", b"fake-audio-bytes", "audio/webm")},
        headers=auth_headers(doctor),
    )
    assert resp.status_code == 502


def test_any_authenticated_role_can_call_it(client, make_user, auth_headers, monkeypatch):
    """Stateless utility endpoint used by Doctor (OPD), Nurse/NursingStation (IPD), and
    HeadNurse -- no role gate, matching /api/scribe and /api/clinical-helper."""
    _mock_transcribe(monkeypatch, text="ok")
    nurse = make_user(email="nurse@transcribe-audio.com", role="Nurse")
    resp = client.post(
        "/api/transcribe-audio",
        files={"audio": ("r.webm", b"fake-audio-bytes", "audio/webm")},
        headers=auth_headers(nurse),
    )
    assert resp.status_code == 200
