"""
Application configuration for Ujjwal Rail assistant.
All thresholds, TTLs, and operational flags are centralized here.
"""

import os
from typing import Optional
from pydantic import BaseModel


def load_env_file(filepath: Optional[str] = None) -> None:
    """Loads key=value pairs from a .env file into os.environ if not already set."""
    if not filepath:
        # Look in project root directory
        filepath = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass


# Automatically load project .env on configuration load
load_env_file()


class AppConfig(BaseModel):
    # Operating environment
    MOCK_LLM: bool = os.getenv("MOCK_LLM", "false").lower() == "true"
    MAX_PARTS: int = 3
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")

    # Grok (xAI) LLM Configuration
    GROK_API_KEY: str = os.getenv("GROK_API_KEY", "")
    GROK_BASE_URL: str = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")
    GROK_MODEL: str = os.getenv("GROK_MODEL", "grok-2-latest")

    # Database
    DB_PATH: str = os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ujjwal_rail.db")
    )

    # Retrieval and Router thresholds (never LLM self-confidence)
    T_RETRIEVAL: float = 0.05
    T_ROUTER: float = 0.60
    MAX_CLARIFICATIONS: int = 2

    # Action TTL default (minutes, will be checked against settings)
    DEFAULT_ACTION_TTL_MINUTES: int = 10


config = AppConfig()
