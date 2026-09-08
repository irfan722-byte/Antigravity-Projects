"""Application settings.

All secrets come from the environment. Nothing secret is hard-coded here.
User-specific trading preferences (timezone, risk limits, Friday cutoff) are NOT
settings: they live per user in the database (see db/models.py UserSettings) and
the values below are only the initial defaults applied during onboarding.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path(__file__).parent / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "paper", "production"] = "development"
    app_name: str = "AurumGuard"
    log_level: str = "INFO"

    # --- storage ---
    database_url: str = "sqlite:///./aurumguard.db"
    redis_url: str | None = None
    audit_dir: str = "./data/audit"

    # --- security ---
    secret_key: str = Field(default="dev-only-insecure-secret-change-me", min_length=16)
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 120

    # --- providers (mock is the default; nothing paid is required to run) ---
    market_data_provider: Literal["mock", "twelvedata"] = "mock"
    calendar_provider: Literal["mock", "none"] = "mock"
    macro_provider: Literal["mock", "fred"] = "mock"
    news_provider: Literal["mock", "none"] = "mock"
    push_provider: Literal["mock", "webpush"] = "mock"
    twelvedata_api_key: str | None = None
    fred_api_key: str | None = None
    # Twelve Data credit control (see app/providers/twelvedata.py): the UI is served a cached quote up to
    # this many seconds old; the analysis loop always requests a fresh one. Spread is a paper-trading cost
    # assumption because the price endpoint is mid-only; 0 reports a zero spread and flags it.
    twelvedata_quote_ttl_seconds: float = 300.0
    twelvedata_assumed_spread_usd: float = 0.30

    # --- push (VAPID) ---
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"

    # --- analysis loop ---
    analysis_interval_seconds: int = 60
    analysis_enabled: bool = True

    # --- onboarding defaults (copied into UserSettings, then user-editable) ---
    default_timezone: str = "Asia/Dubai"
    default_account_currency: Literal["USD", "AED"] = "USD"
    default_friday_cutoff_local: str = "20:00"
    usd_aed_rate: float = 3.6725  # UAE dirham peg; used for display conversion only

    @field_validator("secret_key")
    @classmethod
    def _no_dev_secret_in_prod(cls, v: str, info):  # type: ignore[no-untyped-def]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_for_environment(self) -> list[str]:
        """Return a list of configuration problems for the current environment."""
        problems: list[str] = []
        if self.app_env in ("staging", "paper", "production"):
            if self.secret_key.startswith("dev-only"):
                problems.append("SECRET_KEY must be set to a strong value outside development")
            if self.database_url.startswith("sqlite"):
                problems.append("SQLite is not supported outside development/test; set DATABASE_URL")
            if self.push_provider == "webpush" and not (self.vapid_public_key and self.vapid_private_key):
                problems.append("VAPID keys are required when PUSH_PROVIDER=webpush")
        if self.market_data_provider == "twelvedata" and not self.twelvedata_api_key:
            problems.append("TWELVEDATA_API_KEY is required when MARKET_DATA_PROVIDER=twelvedata")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_json_config(name: str) -> dict:
    """Load a versioned JSON configuration file from app/config."""
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
