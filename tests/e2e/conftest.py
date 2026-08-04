"""
Fixtures for real-browser (Playwright) end-to-end tests. These drive the actual
frontend/*.html + JS against a real listening HTTP server (Playwright cannot talk to an
in-process ASGI TestClient), which is the only way to catch pure-frontend bugs like a `const`
being reassigned in apiRequest() -- something no backend-only pytest test can ever exercise.

Reuses the SAME already-imported `app.main` module (and its throwaway SQLite engine) that the
top-level tests/conftest.py set up -- Python caches that import, so there is no way to get a
second independently-configured copy within one pytest process, and there's no need to: the
top-level `_clean_database` autouse fixture already resets tables before every test, e2e
included.

The actual "simulate voice input" mechanics (mock MediaRecorder, canned-transcript queuing,
token minting, live server bootstrap) live in tests/_voice_helpers.py, shared with the
standalone scale-test runner (tests/scale/runner.py) so there's exactly one implementation of
each -- re-exported here for the existing test files that import them from this module.
"""
import pytest

from tests._voice_helpers import (  # noqa: F401  (re-exported for existing e2e test imports)
    MOCK_MEDIA_RECORDER_INIT_SCRIPT,
    mint_tokens,
    mock_transcription_network_failure,
    queue_transcription_result,
    set_tokens_in_browser,
    start_live_server,
)

REQUIRES_BROWSER = pytest.mark.e2e


@pytest.fixture(scope="session")
def live_server_url():
    from app import main as app_main

    base_url, stop = start_live_server(app_main.app)
    yield base_url
    stop()


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "permissions": ["microphone"]}


@pytest.fixture
def js_page(page):
    """A Playwright `page` with MediaRecorder/getUserMedia mocked before any script runs,
    and JS errors captured so tests can assert the app never throws (that's exactly the class
    of bug this suite exists to catch)."""
    page.add_init_script(MOCK_MEDIA_RECORDER_INIT_SCRIPT)
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.js_errors = errors
    return page


def mint_expired_access_token(user):
    """An access token whose `exp` is already in the past, so the very first API call the
    page makes triggers apiRequest()'s 401 -> refresh path -- deterministic, no real waiting
    for the (15-minute default) ACCESS_TOKEN_EXPIRE_MINUTES to elapse."""
    from datetime import datetime, timedelta
    from jose import jwt as jose_jwt
    from app.config import settings

    token_data = {
        "user_id": user.id, "email": user.email, "role": user.role,
        "organization_id": user.organization_id,
    }
    return jose_jwt.encode(
        {**token_data, "exp": datetime.utcnow() - timedelta(minutes=1), "type": "access"},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )
