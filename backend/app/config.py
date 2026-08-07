import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./aivana.db"
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # Higher-limit developer-tier key, kept as a separate .env entry rather than overwriting
    # GROQ_API_KEY directly so the original key stays available/documented as a fallback.
    GROQ_API_KEY_Prod: str = os.getenv("GROQ_API_KEY_Prod", "")
    GROQ_MODEL: str = "qwen/qwen3.6-27b"
    # Whisper model used for POST /api/transcribe-audio (see scribe.py's transcribe_audio) --
    # a separate setting from GROQ_MODEL since it's a different model for a different Groq
    # endpoint. MUST be "whisper-large-v3", not "-turbo" or "distil-whisper-large-v3-en":
    # transcribe_audio calls Groq's /audio/TRANSLATIONS endpoint specifically (not
    # /audio/transcriptions), and Groq's hosted translations task only supports the full
    # whisper-large-v3 model -- the turbo/distilled variants are transcription-only there.
    # Tried "-turbo" here for a real, wanted latency win (see git history) and it broke
    # transcription in production ("Transcription failed" on every recording, confirmed live)
    # -- reverted same-day. If a faster audio path is wanted later, it has to come from
    # switching endpoints (transcriptions + explicit language handling) or a different
    # provider/local model, not from swapping the model on this same endpoint.
    GROQ_AUDIO_MODEL: str = os.getenv("GROQ_AUDIO_MODEL", "whisper-large-v3")
    # Comma-separated list of origins allowed to call the API. The frontend is same-origin
    # (served by this same FastAPI process, API_BASE = '/api'), so this only matters for local
    # dev on a different port/live-server and any future separately-hosted frontend.
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    # Disabled in tests (tests/conftest.py, tests/scale/runner.py) -- many legitimate tests
    # fire dozens of auth calls from the same test-client "IP" in well under a minute.
    RATE_LIMIT_ENABLED: bool = True

    class Config:
        env_file = ".env"

settings = Settings()
# Prefer the developer-tier key (higher rate limits) whenever it's configured; every caller
# in the app reads settings.GROQ_API_KEY, so this is the one place that needs to know both
# exist.
if settings.GROQ_API_KEY_Prod:
    settings.GROQ_API_KEY = settings.GROQ_API_KEY_Prod

_INSECURE_DEFAULT_SECRET_KEY = "your-super-secret-key-change-this-in-production"
if settings.SECRET_KEY == _INSECURE_DEFAULT_SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is still the well-known FastAPI tutorial default. Anyone who knows this "
        "value can forge a valid JWT for any user/role. Set a real random SECRET_KEY in "
        "backend/.env (e.g. `python -c \"import secrets; print(secrets.token_hex(32))\"`) or "
        "the SECRET_KEY environment variable before starting the app."
    )