"""
Unit tests for app.scribe.ScribeEngine.transcribe_audio -- the Groq Whisper
(/audio/translations) call backing POST /api/transcribe-audio (see main.py). Mirrors
test_scribe_json_parsing.py's style: fake requests.post response objects, no network calls,
and reuses the same _post_with_retry plumbing _call_groq_api's retry tests already exercise,
so the retry/PHI-logging tests here focus on behavior specific to the audio call (multipart
fields, the {"text":...} response shape, which differs from chat completions).
"""
import logging

import pytest

from app.scribe import ScribeEngine


@pytest.fixture
def engine():
    e = ScribeEngine()
    e.api_key = "some-key"
    return e


class _Success:
    status_code = 200

    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"text": self._text}


def test_transcribe_audio_posts_multipart_file_and_model(monkeypatch, engine):
    seen = {}

    def _fake_post(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return _Success("Patient has acidity for 5 days, prescribe Pantop 40mg tablet OD")

    monkeypatch.setattr("app.scribe.requests.post", _fake_post)

    result = engine.transcribe_audio(b"fake-audio-bytes", "audio/webm", "recording.webm")

    assert result == "Patient has acidity for 5 days, prescribe Pantop 40mg tablet OD"
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/translations"
    filename, content, content_type = seen["kwargs"]["files"]["file"]
    assert filename == "recording.webm"
    assert content == b"fake-audio-bytes"
    assert content_type == "audio/webm"
    assert seen["kwargs"]["data"]["model"] == engine.audio_model


def test_transcribe_audio_strips_surrounding_whitespace(monkeypatch, engine):
    monkeypatch.setattr("app.scribe.requests.post", lambda *a, **k: _Success("  hello there  "))
    assert engine.transcribe_audio(b"x", "audio/webm", "r.webm") == "hello there"


def test_transcribe_audio_missing_text_key_returns_empty_string(monkeypatch, engine):
    class _NoText:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    monkeypatch.setattr("app.scribe.requests.post", lambda *a, **k: _NoText())
    assert engine.transcribe_audio(b"x", "audio/webm", "r.webm") == ""


def test_transcribe_audio_raises_without_api_key():
    engine = ScribeEngine()
    engine.api_key = ""
    with pytest.raises(ValueError):
        engine.transcribe_audio(b"x", "audio/webm", "r.webm")


def test_transcribe_audio_retries_on_429_and_succeeds(monkeypatch, engine):
    """The shared _post_with_retry refactor must keep retry-on-429 working for the audio
    call, not just the chat-completions call it was extracted from."""
    calls = []

    class _RateLimited:
        status_code = 429
        headers = {"retry-after": "0.01"}

    def _fake_post(*a, **k):
        calls.append(1)
        return _RateLimited() if len(calls) == 1 else _Success("ok")

    monkeypatch.setattr("app.scribe.requests.post", _fake_post)
    monkeypatch.setattr("app.scribe.time.sleep", lambda *a, **k: None)

    assert engine.transcribe_audio(b"x", "audio/webm", "r.webm") == "ok"
    assert len(calls) == 2


def test_transcribe_audio_propagates_error_after_max_retries(monkeypatch, engine):
    class _RateLimited:
        status_code = 429
        headers = {}

        def raise_for_status(self):
            import requests
            raise requests.exceptions.HTTPError("429 after retries")

    monkeypatch.setattr("app.scribe.requests.post", lambda *a, **k: _RateLimited())
    monkeypatch.setattr("app.scribe.time.sleep", lambda *a, **k: None)

    import requests
    with pytest.raises(requests.exceptions.HTTPError):
        engine.transcribe_audio(b"x", "audio/webm", "r.webm")


def test_transcribe_audio_error_logs_generic_message_not_response_body(monkeypatch, engine, caplog):
    """PHI convention (scribe.py module docstring): a Groq error response body can echo
    request content back, so it must only ever be logged at DEBUG -- ERROR-level logging
    (which a default-configured log aggregator captures) must stay generic."""

    class _ServerError:
        status_code = 500
        text = "upstream detail that could echo request content back"

        def raise_for_status(self):
            import requests
            raise requests.exceptions.HTTPError("500 error", response=self)

    monkeypatch.setattr("app.scribe.requests.post", lambda *a, **k: _ServerError())
    caplog.set_level(logging.ERROR, logger="app.scribe")

    import requests
    with pytest.raises(requests.exceptions.HTTPError):
        engine.transcribe_audio(b"x", "audio/webm", "r.webm")

    assert "upstream detail" not in caplog.text
