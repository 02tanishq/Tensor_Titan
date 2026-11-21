"""
Application configuration for Ujjwal Rail assistant.
All thresholds, TTLs, and operational flags are centralized here.
"""

import os
from pydantic import BaseModel


class AppConfig(BaseModel):
    # Operating environment
    MOCK_LLM: bool = True
    MAX_PARTS: int = 3
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"

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
