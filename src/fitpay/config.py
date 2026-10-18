"""Settings, read from environment variables (or a .env file) prefixed with FITPAY_."""

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PAYFAST_LIVE_URL = "https://www.payfast.co.za/eng/process"
PAYFAST_SANDBOX_URL = "https://sandbox.payfast.co.za/eng/process"


def on_vercel() -> bool:
    # Vercel sets VERCEL=1 in every deployment.
    return os.environ.get("VERCEL") == "1"


def _default_database_url() -> str:
    # Vercel's filesystem is read-only apart from /tmp.
    return "sqlite:////tmp/fitpay.db" if on_vercel() else "sqlite:///./fitpay.db"


def _default_public_url() -> str:
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
    return f"https://{host}" if host else "http://localhost:8000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FITPAY_", env_file=".env", extra="ignore")

    database_url: str = Field(default_factory=_default_database_url)
    # Admin endpoints need this key in the X-API-Key header. Empty means admin is switched off.
    admin_api_key: str = ""
    # The public address of this API, used for PayFast's return, cancel and notify URLs.
    public_url: str = Field(default_factory=_default_public_url)
    # Clients whose paid-up date is this close are flagged "due soon".
    due_soon_days: int = Field(default=7, ge=0, le=60)
    # Load the demo packages and clients on startup if the database is empty.
    # On by default on Vercel, where the database starts empty on every cold start.
    demo: bool = Field(default_factory=on_vercel)

    payfast_merchant_id: str = "10000100"
    payfast_merchant_key: str = "46f0cd694581a"
    payfast_passphrase: str = ""
    payfast_sandbox: bool = True

    @property
    def payfast_process_url(self) -> str:
        return PAYFAST_SANDBOX_URL if self.payfast_sandbox else PAYFAST_LIVE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
