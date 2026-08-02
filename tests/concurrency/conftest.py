"""
Fixtures for real-concurrency tests: a genuinely live uvicorn server (not the in-process
TestClient) hit with real simultaneous HTTP requests via a ThreadPoolExecutor, so the ASGI
app's actual request handling interleaves the way it would under real simultaneous users --
the only way to catch time-of-check-to-time-of-use races that an in-process, single-request
TestClient call can never expose.

Reuses the same throwaway-SQLite-DB safety guard as the rest of the suite (top-level
tests/conftest.py runs first and sets DATABASE_URL before any app import happens).
"""
import socket
import threading
import time

import pytest
import requests


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server_url():
    import uvicorn
    from app import main as app_main

    port = _free_port()
    config = uvicorn.Config(app_main.app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    last_error = None
    for _ in range(100):
        try:
            requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
            break
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(0.2)
    else:
        pytest.fail(f"live concurrency-test server did not start in time: {last_error}")

    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
