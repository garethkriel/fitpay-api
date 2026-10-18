"""Settings and startup behaviour for hosted deployments (Vercel)."""

import pytest
from fastapi.testclient import TestClient

from fitpay.api.app import create_app
from fitpay.config import Settings


def test_home_redirects_to_the_docs(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_vercel_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("FITPAY_DATABASE_URL", "FITPAY_PUBLIC_URL", "FITPAY_DEMO"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "fitpay-api.vercel.app")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url == "sqlite:////tmp/fitpay.db"
    assert settings.public_url == "https://fitpay-api.vercel.app"
    assert settings.demo is True


def test_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("VERCEL", "VERCEL_PROJECT_PRODUCTION_URL", "FITPAY_DATABASE_URL", "FITPAY_DEMO"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url == "sqlite:///./fitpay.db"
    assert settings.demo is False


def test_demo_mode_loads_the_demo_data_on_startup(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"demo": True}))
    with TestClient(app) as client:
        names = [p["name"] for p in client.get("/packages").json()]
    assert len(names) == 5
    assert "12 Week Transformation" in names
