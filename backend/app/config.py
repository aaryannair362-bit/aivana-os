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

    class Config:
        env_file = ".env"

settings = Settings()
# Prefer the developer-tier key (higher rate limits) whenever it's configured; every caller
# in the app reads settings.GROQ_API_KEY, so this is the one place that needs to know both
# exist.
if settings.GROQ_API_KEY_Prod:
    settings.GROQ_API_KEY = settings.GROQ_API_KEY_Prod