from urllib.parse import urlencode

from fastapi.testclient import TestClient

from fitpay import payfast
from tests.conftest import PASSPHRASE


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["payfast"] == "sandbox"


# --- Admin access -----------------------------------------------------------


def test_admin_routes_need_the_api_key(client: TestClient) -> None:
    assert client.get("/clients").status_code == 401
    client.headers["X-API-Key"] = "wrong"
    assert client.get("/clients").status_code == 401


def test_admin_is_switched_off_without_a_key(settings, client: TestClient) -> None:
    client.app.state.settings = settings.model_copy(update={"admin_api_key": ""})
    client.headers["X-API-Key"] = ""
    assert client.get("/clients").status_code == 503


# --- Packages ---------------------------------------------------------------


def test_create_and_list_packages(admin: TestClient, package: dict) -> None:
    assert package["price"] == "R1 000.00"
    admin.post(
        "/packages",
        json={"name": "Old plan", "price_cents": 1, "billing": "monthly", "active": False},
    )
    names = [p["name"] for p in admin.get("/packages").json()]
    assert names == ["Lifestyle Training"]  # inactive packages are hidden from clients


def test_package_names_are_unique(admin: TestClient, package: dict) -> None:
    response = admin.post(
        "/packages", json={"name": "lifestyle training", "price_cents": 5, "billing": "monthly"}
    )
    assert response.status_code == 409


def test_update_package(admin: TestClient, package: dict) -> None:
    response = admin.patch(f"/packages/{package['id']}", json={"price_cents": 110_000})
    assert response.json()["price"] == "R1 100.00"
    assert admin.patch("/packages/999", json={"active": False}).status_code == 404


def test_package_validation(admin: TestClient) -> None:
    response = admin.post(
        "/packages", json={"name": "Free", "price_cents": 0, "billing": "monthly"}
    )
    assert response.status_code == 422


# --- Clients and manual payments --------------------------------------------


def make_client(admin: TestClient, package: dict, **extra) -> dict:
    body = {
        "name": "Thandi Mokoena",
        "email": "Thandi@Example.com",
        "package_id": package["id"],
        "start_date": "2026-09-01",
    } | extra
    response = admin.post("/clients", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_new_client_has_not_paid(admin: TestClient, package: dict) -> None:
    client = make_client(admin, package)
    assert client["email"] == "thandi@example.com"
    assert client["status"] == "not_paid"
    assert client["paid_until"] is None
    assert client["package"] == "Lifestyle Training"


def test_client_emails_are_unique(admin: TestClient, package: dict) -> None:
    make_client(admin, package)
    response = admin.post(
        "/clients",
        json={"name": "Someone", "email": "thandi@example.com", "start_date": "2026-01-01"},
    )
    assert response.status_code == 409


def test_manual_payments_move_paid_until_forward(admin: TestClient, package: dict) -> None:
    client = make_client(admin, package)
    payment = {"amount_cents": 100_000, "months": 1, "method": "eft", "paid_on": "2026-09-01"}

    after_one = admin.post(f"/clients/{client['id']}/payments", json=payment).json()
    assert after_one["paid_until"] == "2026-10-01"
    assert after_one["status"] == "overdue"  # "today" in the tests is 2026-10-18

    after_two = admin.post(
        f"/clients/{client['id']}/payments", json=payment | {"method": "cash"}
    ).json()
    assert after_two["paid_until"] == "2026-11-01"
    assert after_two["status"] == "up_to_date"
    assert [p["method"] for p in after_two["payments"]] == ["eft", "cash"]
    assert after_two["payments"][0]["amount"] == "R1 000.00"


def test_manual_payment_cannot_claim_to_be_payfast(admin: TestClient, package: dict) -> None:
    client = make_client(admin, package)
    response = admin.post(
        f"/clients/{client['id']}/payments",
        json={"amount_cents": 100, "method": "payfast", "paid_on": "2026-10-01"},
    )
    assert response.status_code == 409


def test_list_clients_puts_people_who_owe_first_and_filters(
    admin: TestClient, package: dict
) -> None:
    paid = make_client(admin, package, name="Zanele Up", email="z@example.com")
    admin.post(
        f"/clients/{paid['id']}/payments",
        json={"amount_cents": 100_000, "months": 3, "paid_on": "2026-09-01"},
    )
    make_client(admin, package, name="Adam Owes", email="a@example.com")

    rows = admin.get("/clients").json()
    assert [(r["name"], r["status"]) for r in rows] == [
        ("Adam Owes", "not_paid"),
        ("Zanele Up", "up_to_date"),
    ]
    assert [r["name"] for r in admin.get("/clients?status=up_to_date").json()] == ["Zanele Up"]
    assert [r["name"] for r in admin.get("/clients?search=ADAM").json()] == ["Adam Owes"]


def test_archive_hides_a_client(admin: TestClient, package: dict) -> None:
    client = make_client(admin, package)
    admin.patch(f"/clients/{client['id']}", json={"archived": True})
    assert admin.get("/clients").json() == []
    assert len(admin.get("/clients?include_archived=true").json()) == 1


def test_missing_client_is_404(admin: TestClient) -> None:
    assert admin.get("/clients/42").status_code == 404


# --- PayFast checkout and notifications -------------------------------------


def start_checkout(client: TestClient, package: dict, email: str = "lerato@example.com") -> dict:
    response = client.post(
        "/checkout",
        json={
            "package_id": package["id"],
            "first_name": "Lerato",
            "last_name": "Dlamini",
            "email": email,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def notify(
    client: TestClient,
    checkout: dict,
    *,
    status: str = "COMPLETE",
    amount: str = "1000.00",
    pf_payment_id: str = "1089250",
    passphrase: str = PASSPHRASE,
):
    fields = [
        ("m_payment_id", checkout["reference"]),
        ("pf_payment_id", pf_payment_id),
        ("payment_status", status),
        ("item_name", "Lifestyle Training"),
        ("amount_gross", amount),
        ("amount_fee", "-23.00"),
        ("amount_net", "977.00"),
        ("merchant_id", "10000100"),
    ]
    fields.append(("signature", payfast.sign(fields, passphrase, skip_blank=False)))
    return client.post(
        "/payfast/notify",
        content=urlencode(fields),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_checkout_builds_a_signed_payfast_form(client: TestClient, package: dict) -> None:
    checkout = start_checkout(client, package)
    fields = checkout["fields"]
    assert checkout["action_url"] == "https://sandbox.payfast.co.za/eng/process"
    assert fields["amount"] == "1000.00"
    assert fields["m_payment_id"] == checkout["reference"]
    assert fields["notify_url"] == "https://fitpay.example.com/payfast/notify"
    unsigned = [(k, v) for k, v in fields.items() if k != "signature"]
    assert fields["signature"] == payfast.sign(unsigned, PASSPHRASE)


def test_paid_notification_completes_the_payment(admin: TestClient, package: dict) -> None:
    checkout = start_checkout(admin, package)
    assert admin.get(f"/payments/{checkout['reference']}/done").json()["status"] == "pending"

    response = notify(admin, checkout)
    assert response.status_code == 200
    assert response.text == "OK"
    assert admin.get(f"/payments/{checkout['reference']}/done").json()["status"] == "complete"

    client_row = admin.get("/clients").json()[0]
    assert client_row["email"] == "lerato@example.com"
    assert client_row["status"] == "up_to_date"  # started today, paid one month


def test_repeated_notification_is_harmless(admin: TestClient, package: dict) -> None:
    checkout = start_checkout(admin, package)
    assert notify(admin, checkout).status_code == 200
    assert notify(admin, checkout).status_code == 200  # PayFast retries
    client_id = admin.get("/clients").json()[0]["id"]
    assert len(admin.get(f"/clients/{client_id}").json()["payments"]) == 1


def test_second_payfast_payment_for_same_reference_is_refused(
    admin: TestClient, package: dict
) -> None:
    checkout = start_checkout(admin, package)
    notify(admin, checkout)
    assert notify(admin, checkout, pf_payment_id="999").status_code == 409


def test_notification_with_wrong_signature_changes_nothing(
    admin: TestClient, package: dict
) -> None:
    checkout = start_checkout(admin, package)
    assert notify(admin, checkout, passphrase="guess").status_code == 400
    assert admin.get(f"/payments/{checkout['reference']}/done").json()["status"] == "pending"


def test_notification_with_wrong_amount_is_refused(admin: TestClient, package: dict) -> None:
    checkout = start_checkout(admin, package)
    assert notify(admin, checkout, amount="1.00").status_code == 400
    assert admin.get(f"/payments/{checkout['reference']}/done").json()["status"] == "pending"


def test_cancelled_notification(admin: TestClient, package: dict) -> None:
    checkout = start_checkout(admin, package)
    notify(admin, checkout, status="CANCELLED")
    assert admin.get(f"/payments/{checkout['reference']}/cancelled").json()["status"] == "cancelled"


def test_checkout_reuses_an_existing_client(admin: TestClient, package: dict) -> None:
    start_checkout(admin, package)
    start_checkout(admin, package, email="LERATO@example.com")
    assert len(admin.get("/clients").json()) == 1


def test_checkout_for_inactive_package_is_refused(admin: TestClient, package: dict) -> None:
    admin.patch(f"/packages/{package['id']}", json={"active": False})
    response = admin.post(
        "/checkout",
        json={"package_id": package["id"], "first_name": "A", "last_name": "B", "email": "a@b.co"},
    )
    assert response.status_code == 409


# --- Reports ----------------------------------------------------------------


def test_reports(admin: TestClient, package: dict) -> None:
    client = make_client(admin, package)
    for paid_on in ("2026-08-03", "2026-09-01", "2026-09-20"):
        admin.post(
            f"/clients/{client['id']}/payments",
            json={"amount_cents": 100_000, "paid_on": paid_on},
        )
    checkout = start_checkout(admin, package)  # still pending, so not counted

    revenue = admin.get("/reports/revenue?year=2026").json()
    assert revenue == [
        {"month": "2026-08", "payments": 1, "total_cents": 100_000, "total": "R1 000.00"},
        {"month": "2026-09", "payments": 2, "total_cents": 200_000, "total": "R2 000.00"},
    ]
    assert admin.get("/reports/revenue?year=2025").json() == []

    csv_text = admin.get("/reports/payments.csv").text
    lines = csv_text.strip().splitlines()
    assert lines[0] == "paid_on,client,email,amount,months,method,reference"
    assert len(lines) == 4
    assert checkout["reference"] not in csv_text

    assert admin.get("/reports/overdue").json() == []  # paid 3 months from 1 Sept: up to date
