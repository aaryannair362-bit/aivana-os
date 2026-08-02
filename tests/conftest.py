"""
Shared pytest fixtures for the AIVANA test suite.

SAFETY-CRITICAL: backend/.env's DATABASE_URL points at a real Postgres instance.
backend/app/main.py runs `Base.metadata.create_all(bind=engine)` at IMPORT TIME, so importing
that module is enough to open a connection and issue DDL against whatever DATABASE_URL is
active in the environment. The block below sets an isolated, throwaway SQLite DATABASE_URL
(and dummy secrets so config.py never falls back to backend/.env for anything sensitive)
BEFORE backend.app.main (or anything that imports it) is ever imported. Do not reorder this.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEST_DB_DIR = tempfile.mkdtemp(prefix="aivana_test_db_")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_aivana.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["GROQ_API_KEY"] = "test-dummy-groq-key"
os.environ["GROQ_MODEL"] = "test-model"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as app_main  # noqa: E402  (import must follow env-var setup above)
from app import auth as app_auth  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_database():
    """Drop and recreate all tables before every test for full isolation."""
    Base.metadata.drop_all(bind=app_main.engine)
    Base.metadata.create_all(bind=app_main.engine)
    yield
    Base.metadata.drop_all(bind=app_main.engine)
    Base.metadata.create_all(bind=app_main.engine)


@pytest.fixture
def db_session():
    session = app_main.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _no_live_groq_calls(monkeypatch):
    """
    Default safety net: any test that doesn't explicitly stub scribe._call_groq_api gets a
    RuntimeError instead of silently making a real network call to Groq with test data.
    Individual tests override via monkeypatch.setattr(app_main.scribe, "_call_groq_api", ...).
    """
    def _blocked(*args, **kwargs):
        raise RuntimeError(
            "Test attempted a live Groq API call without mocking scribe._call_groq_api. "
            "Mock it explicitly, or use the llm_integration marker for intentional live calls."
        )
    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _blocked)


@pytest.fixture
def client():
    with TestClient(app_main.app) as c:
        yield c


@pytest.fixture
def make_user(db_session):
    """Factory fixture: make_user(email=..., password=..., role=..., organization_id=...)."""
    from app.models import Organization, User, PasswordHistory

    def _make(email, password="Str0ng!Passw0rd#1", role="Admin", organization_id=None, status="Active"):
        if organization_id is None:
            org = Organization(name=f"Org for {email}")
            db_session.add(org)
            db_session.flush()
            organization_id = org.id
        password_hash = app_auth.get_password_hash(password)
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            organization_id=organization_id,
            status=status,
        )
        db_session.add(user)
        db_session.flush()
        db_session.add(PasswordHistory(user_id=user.id, password_hash=password_hash))
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture
def auth_headers():
    """Factory fixture: auth_headers(user) -> {"Authorization": "Bearer ..."}."""
    def _headers(user):
        token_data = {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "organization_id": user.organization_id,
        }
        token = app_auth.create_access_token(token_data)
        return {"Authorization": f"Bearer {token}"}

    return _headers


def mock_groq_json(monkeypatch, payload_or_raw):
    """
    Test helper (not a fixture): patch app_main.scribe._call_groq_api to return either a raw
    string (payload_or_raw is a str) or a dict that will be json.dumps'd as the "model output".
    """
    import json as _json

    if isinstance(payload_or_raw, str):
        raw = payload_or_raw
    else:
        raw = _json.dumps(payload_or_raw)

    def _fake(prompt, system=None, temperature=0.3):
        return raw

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake)
