"""
Central configuration.

All settings are read from environment variables (or a local .env file).
Never hardcode secrets — the MiniMax API key is injected via env / k8s Secret.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Service ----
    app_name: str = "scalable-llm-engine"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # ---- MiniMax (OpenAI-compatible API) ----
    # Get a key at https://platform.minimax.io  (User Center -> Interface Key)
    minimax_api_key: str = Field(default="")
    minimax_base_url: str = Field(default="https://api.minimax.io/v1")
    # Default model for general/complex reasoning. Cheaper/faster routes can
    # override per-request (see app/providers/minimax.py MODEL_ROUTES).
    minimax_default_model: str = Field(default="MiniMax-M2.5")
    request_timeout_seconds: float = Field(default=60.0)
    max_retries: int = Field(default=3)

    # ---- Redis (cache + queue + cost counters) ----
    redis_url: str = Field(default="redis://localhost:6379/0")
    cache_ttl_seconds: int = Field(default=3600)
    cache_enabled: bool = Field(default=True)

    # ---- Queue ----
    queue_name: str = Field(default="llm:jobs")
    job_result_ttl_seconds: int = Field(default=86400)  # keep results 24h
    worker_poll_timeout: int = Field(default=5)  # BLPOP block timeout (s)

    # ---- Rate / safety guards ----
    max_prompt_chars: int = Field(default=120_000)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
