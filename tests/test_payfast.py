import hashlib

import pytest

from fitpay import payfast


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def test_signature_matches_payfast_rules_written_out_by_hand() -> None:
    pairs = [
        ("merchant_id", "10000100"),
        ("merchant_key", "46f0cd694581a"),
        ("return_url", "https://example.com/return?a=1&b=2"),
        ("name_first", "  Gareth  "),
        ("name_last", ""),
        ("amount", "100.00"),
        ("item_name", "12 Week Transformation"),
    ]
    expected = md5(
        "merchant_id=10000100&merchant_key=46f0cd694581a"
        "&return_url=https%3A%2F%2Fexample.com%2Freturn%3Fa%3D1%26b%3D2"
        "&name_first=Gareth&amount=100.00&item_name=12+Week+Transformation"
        "&passphrase=jt7NOE43FZPn"
    )
    assert payfast.sign(pairs, "jt7NOE43FZPn") == expected


def test_signature_without_passphrase_leaves_it_off() -> None:
    assert payfast.sign([("amount", "5.00")]) == md5("amount=5.00")


def test_notification_signature_keeps_blank_fields() -> None:
    pairs = [("a", "1"), ("b", ""), ("c", "x y")]
    assert payfast.sign(pairs, skip_blank=False) == md5("a=1&b=&c=x+y")


def test_checkout_fields_are_ordered_and_signed() -> None:
    req = payfast.CheckoutRequest(
        merchant_id="10000100",
        merchant_key="46f0cd694581a",
        return_url="https://x.test/done",
        cancel_url="https://x.test/cancel",
        notify_url="https://x.test/notify",
        first_name="Thandi",
        last_name="Mokoena",
        email="thandi@example.com",
        reference="abc123",
        amount_cents=120_050,
        item_name="Month-to-Month Program",
    )
    fields = payfast.checkout_fields(req, "secret")
    keys = [k for k, _ in fields]
    assert keys[0] == "merchant_id"
    assert keys[-1] == "signature"
    assert dict(fields)["amount"] == "1200.50"
    assert dict(fields)["signature"] == payfast.sign(fields[:-1], "secret")


@pytest.mark.parametrize(
    ("text", "cents"), [("100.00", 10_000), ("100", 10_000), ("0.5", 50), ("12.34", 1234)]
)
def test_amount_to_cents(text: str, cents: int) -> None:
    assert payfast.amount_to_cents(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "1.234", "-5.00", "1,000.00", "1.2.3"])
def test_amount_to_cents_rejects_bad_input(text: str) -> None:
    with pytest.raises(ValueError):
        payfast.amount_to_cents(text)


def signed_notification(fields: list[tuple[str, str]], passphrase: str) -> list[tuple[str, str]]:
    return [*fields, ("signature", payfast.sign(fields, passphrase, skip_blank=False))]


BASE_FIELDS = [
    ("m_payment_id", "ref-1"),
    ("pf_payment_id", "1089250"),
    ("payment_status", "COMPLETE"),
    ("item_name", "Lifestyle Training"),
    ("amount_gross", "1000.00"),
    ("amount_fee", "-23.00"),
    ("amount_net", "977.00"),
    ("custom_str1", ""),
    ("merchant_id", "10000100"),
]


def test_verify_notification_accepts_a_correctly_signed_one() -> None:
    note = payfast.verify_notification(
        signed_notification(BASE_FIELDS, "pw"), merchant_id="10000100", passphrase="pw"
    )
    assert note.reference == "ref-1"
    assert note.pf_payment_id == "1089250"
    assert note.payment_status == "COMPLETE"
    assert note.amount_cents == 100_000


def test_verify_notification_rejects_a_tampered_amount() -> None:
    pairs = signed_notification(BASE_FIELDS, "pw")
    tampered = [(k, "1.00" if k == "amount_gross" else v) for k, v in pairs]
    with pytest.raises(payfast.InvalidNotification, match="signature"):
        payfast.verify_notification(tampered, merchant_id="10000100", passphrase="pw")


def test_verify_notification_rejects_the_wrong_passphrase() -> None:
    with pytest.raises(payfast.InvalidNotification):
        payfast.verify_notification(
            signed_notification(BASE_FIELDS, "pw"), merchant_id="10000100", passphrase="other"
        )


def test_verify_notification_rejects_another_merchant() -> None:
    with pytest.raises(payfast.InvalidNotification, match="merchant"):
        payfast.verify_notification(
            signed_notification(BASE_FIELDS, "pw"), merchant_id="99999", passphrase="pw"
        )


def test_verify_notification_rejects_a_missing_signature() -> None:
    with pytest.raises(payfast.InvalidNotification):
        payfast.verify_notification(BASE_FIELDS, merchant_id="10000100", passphrase="pw")
