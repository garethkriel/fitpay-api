"""Settings, read from environment variables (or a .env file) prefixed with FITPAY_."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PAYFAST_LIVE_URL = "https://www.payfast.co.za/eng/process"
PAYFAST_SANDBOX_URL = "https://sandbox.payfast.co.za/eng/process"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FITPAY_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./fitpay.db"
    # Admin endpoints need this key in the X-API-Key header. Empty means admin is switched off.
    admin_api_key: str = ""
    # The public address of this API, used for PayFast's return, cancel and notify URLs.
    public_url: str = "http://localhost:8000"
    # Clients whose paid-up date is this close are flagged "due soon".
    due_soon_days: int = Field(default=7, ge=0, le=60)

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
