"""
Re-exports the e2e browser/live-server fixtures for tests/scenarios/ -- pytest's conftest
fixture discovery is scoped to a directory and its subdirectories, so tests/e2e/conftest.py's
fixtures aren't automatically visible to this sibling directory without this import.
"""
from tests.e2e.conftest import browser_context_args, js_page, live_server_url  # noqa: F401
