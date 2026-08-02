"""
Unit tests for JWT creation/decoding in app.auth. No DB or network involved.
"""
from datetime import datetime, timedelta

from jose import jwt as jose_jwt

from app import auth as app_auth
from app.config import settings


SAMPLE_TOKEN_DATA = {"user_id": 1, "email": "doc@example.com", "role": "Doctor", "organization_id": 5}


def test_access_token_round_trips_claims():
    token = app_auth.create_access_token(SAMPLE_TOKEN_DATA)
    payload = app_auth.decode_token(token)
    assert payload["user_id"] == 1
    assert payload["email"] == "doc@example.com"
    assert payload["role"] == "Doctor"
    assert payload["organization_id"] == 5
    assert payload["type"] == "access"


def test_refresh_token_round_trips_and_is_typed_refresh():
    token = app_auth.create_refresh_token(SAMPLE_TOKEN_DATA)
    payload = app_auth.decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["user_id"] == 1


def test_access_and_refresh_tokens_are_distinguishable():
    access = app_auth.create_access_token(SAMPLE_TOKEN_DATA)
    refresh = app_auth.create_refresh_token(SAMPLE_TOKEN_DATA)
    assert app_auth.decode_token(access)["type"] == "access"
    assert app_auth.decode_token(refresh)["type"] == "refresh"


def test_decode_garbage_token_returns_empty_dict_not_raise():
    payload = app_auth.decode_token("this.is.not-a-jwt")
    assert payload == {}


def test_decode_token_signed_with_wrong_secret_returns_empty_dict():
    forged = jose_jwt.encode(
        {**SAMPLE_TOKEN_DATA, "exp": datetime.utcnow() + timedelta(minutes=5), "type": "access"},
        "a-completely-different-secret",
        algorithm=settings.ALGORITHM,
    )
    assert app_auth.decode_token(forged) == {}


def test_decode_expired_token_returns_empty_dict():
    expired = jose_jwt.encode(
        {**SAMPLE_TOKEN_DATA, "exp": datetime.utcnow() - timedelta(minutes=1), "type": "access"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    assert app_auth.decode_token(expired) == {}


def test_get_current_user_rejects_refresh_token_used_as_access_token():
    """
    A refresh token should never be usable to authenticate a request -- get_current_user
    explicitly checks payload.get("type") == "access".
    """
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    refresh = app_auth.create_refresh_token(SAMPLE_TOKEN_DATA)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=refresh)
    try:
        app_auth.get_current_user(creds)
        assert False, "expected HTTPException for refresh token used as access token"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_get_current_user_accepts_valid_access_token():
    from fastapi.security import HTTPAuthorizationCredentials

    access = app_auth.create_access_token(SAMPLE_TOKEN_DATA)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access)
    user = app_auth.get_current_user(creds)
    assert user["email"] == "doc@example.com"
    assert user["role"] == "Doctor"
