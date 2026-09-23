"""
config.py — AgriSaathi Edge AI
Centralised environment variable handling via pydantic-settings.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    # ── Groq AI ────────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    groq_text_model: str = "openai/gpt-oss-120b"
    groq_vision_model: str = "qwen/qwen3.8-27b"

    # ── Server ─────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8080

    # ── Chatbot ────────────────────────────────────────────────────────────────
    chat_history_max: int = 20

    # ── Misc ───────────────────────────────────────────────────────────────────
    app_title: str = "AgriSaathi Edge AI"
    field_name: str = "Seethariguda Field 01 (Telangana)"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
