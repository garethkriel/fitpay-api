from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from fitpay.api.app import create_app
from fitpay.api.deps import get_today
from fitpay.config import Settings

TODAY = date(2026, 10, 18)
API_KEY = "test-admin-key"
PASSPHRASE = "test-passphrase"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        admin_api_key=API_KEY,
        public_url="https://fitpay.example.com",
        payfast_merchant_id="10000100",
        payfast_merchant_key="46f0cd694581a",
        payfast_passphrase=PASSPHRASE,
        payfast_sandbox=True,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(client: TestClient) -> TestClient:
    client.headers["X-API-Key"] = API_KEY
    return client


@pytest.fixture
def package(admin: TestClient) -> dict[str, object]:
    response = admin.post(
        "/packages",
        json={"name": "Lifestyle Training", "price_cents": 100_000, "billing": "monthly"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body
