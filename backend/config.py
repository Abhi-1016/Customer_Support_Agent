import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

ENV_PATH = Path(__file__).resolve().parent / ".env"

class Settings(BaseSettings):
    # Gemini / Antigravity
    GEMINI_API_KEY: str = Field(..., description="API key for Gemini/Antigravity")
    GEMINI_MODEL: str = Field(default="gemini-3.5-flash-lite")
    GOOGLE_GENAI_USE_VERTEXAI: bool = Field(default=False)
    GOOGLE_CLOUD_PROJECT: str | None = Field(default=None)
    GOOGLE_CLOUD_LOCATION: str | None = Field(default=None)

    # Gnani Vachana
    GNANI_API_KEY: str = Field(..., description="API key for Gnani Vachana")
    GNANI_STT_MODEL: str = Field(default="prisma-v2.5")
    GNANI_TTS_MODEL: str = Field(default="timbre-v2.5")
    GNANI_TTS_VOICE: str = Field(default="sia")
    GNANI_DEFAULT_LANGUAGE: str = Field(default="en-IN")

    # App
    COMPANY_NAME: str = Field(default="ShopSphere")
    BACKEND_PORT: int = Field(default=8000)
    FRONTEND_URL: str = Field(default="http://localhost:3000")
    JWT_SECRET: str = Field(default="4f8b2c9d1e3a5f7b9c1d3e5a7b9c1d3e5a7b9c1d3e5a7b9c1d3e5a7b9c1d3e5a")
    RETURN_WINDOW_DAYS: int = Field(default=10)
    TRANSCRIPT_RETENTION_DAYS: int = Field(default=30)
    LOG_LEVEL: str = Field(default="INFO")
    DEMO_MODE: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore"
    )

def get_settings() -> Settings:
    try:
        settings = Settings()
        # Non-negotiable check: validate presence of GEMINI_API_KEY and GNANI_API_KEY
        if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
            print("CRITICAL CONFIGURATION ERROR: GEMINI_API_KEY is missing or empty.", file=sys.stderr)
            sys.exit(1)
        if not settings.GNANI_API_KEY or not settings.GNANI_API_KEY.strip():
            print("CRITICAL CONFIGURATION ERROR: GNANI_API_KEY is missing or empty.", file=sys.stderr)
            sys.exit(1)
        return settings
    except Exception as exc:
        print(f"CRITICAL CONFIGURATION ERROR: Could not load configuration: {exc}", file=sys.stderr)
        sys.exit(1)

settings = get_settings()

