"""
Shared "simulate voice input" mechanics, used by BOTH the pytest e2e suite (tests/e2e/) and
the standalone scale-test runner (tests/scale/runner.py). There is exactly one implementation
of "how do we make a browser believe it heard speech" -- every test and every scale scenario
goes through a mocked SpeechRecognition event fired at a real browser page, never a raw
transcript POSTed straight to the API bypassing the voice UI.
"""
import socket
import threading
import time

import requests

MOCK_SPEECH_RECOGNITION_INIT_SCRIPT = """
window.__mockInstances = [];
class MockSpeechRecognition {
    constructor() {
        this.continuous = false;
        this.interimResults = false;
        this.lang = '';
        this.onstart = null;
        this.onresult = null;
        this.onerror = null;
        this.onend = null;
        window.__mockInstances.push(this);
    }
    start() { if (this.onstart) this.onstart(); }
    stop() { if (this.onend) setTimeout(() => this.onend && this.onend(), 5); }
}
window.SpeechRecognition = MockSpeechRecognition;
window.webkitSpeechRecognition = MockSpeechRecognition;
if (!navigator.mediaDevices) { navigator.mediaDevices = {}; }
navigator.mediaDevices.getUserMedia = () => Promise.resolve({ getTracks: () => [] });
"""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_live_server(app, host="127.0.0.1", port=None, health_path="/api/health"):
    """
    Boots a real uvicorn.Server for `app` on a background thread and waits until it answers.
    Returns (base_url, stop_fn). Playwright needs a real listening HTTP server -- it cannot
    talk to an in-process ASGI TestClient the way httpx-based tests do.
    """
    import uvicorn

    port = port or free_port()
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    last_error = None
    for _ in range(100):
        try:
            requests.get(f"{base_url}{health_path}", timeout=2)
            break
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(0.2)
    else:
        raise RuntimeError(f"live server did not start in time: {last_error}")

    def stop():
        server.should_exit = True
        thread.join(timeout=5)

    return base_url, stop


def mint_tokens(user):
    """Real access+refresh token strings for a user, bypassing the HTTP login endpoint."""
    from app import auth as app_auth

    token_data = {
        "user_id": user.id, "email": user.email, "role": user.role,
        "organization_id": user.organization_id,
    }
    return {
        "access_token": app_auth.create_access_token(token_data),
        "refresh_token": app_auth.create_refresh_token(token_data),
    }


def set_tokens_in_browser(page, base_url, access_token, refresh_token):
    page.goto(f"{base_url}/index.html")
    page.evaluate(
        """([access, refresh]) => {
            localStorage.setItem('access_token', access);
            localStorage.setItem('refresh_token', refresh);
        }""",
        [access_token, refresh_token],
    )


def fire_speech_result(page, text: str, is_final: bool = True):
    """Simulate the browser delivering one SpeechRecognition result to the most recently
    created mock recognition instance, matching the shape opd.html/ipd.html's onresult
    handlers expect."""
    page.evaluate(
        """([text, isFinal]) => {
            const rec = window.__mockInstances[window.__mockInstances.length - 1];
            const results = [];
            results[0] = { 0: { transcript: text }, isFinal };
            results.length = 1;
            results.resultIndex = 0;
            rec.onresult({ resultIndex: 0, results });
        }""",
        [text, is_final],
    )


def speak_utterances(page, utterances, delay_ms=80):
    """Fire a sequence of speech-recognition results with a small delay between each,
    mirroring how a real multi-sentence conversation arrives incrementally rather than as
    one giant final blob."""
    for text in utterances:
        fire_speech_result(page, text)
        page.wait_for_timeout(delay_ms)
