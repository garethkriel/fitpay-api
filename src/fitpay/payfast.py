"""PayFast: building checkout forms and checking payment notifications (ITNs).

PayFast signs every request with an MD5 hash of the form fields:
  1. Take the fields in order as "name=value" pairs, joined with "&".
  2. URL-encode each value (spaces become "+", hex codes in upper case).
  3. If you've set a passphrase on your PayFast account, add "&passphrase=...".
  4. MD5 the result.

For checkout forms, blank fields are left out. For notifications, every field PayFast
sent is used in the order it arrived, up to (not including) the signature itself.
See https://developers.payfast.co.za/docs for the full rules.
"""

import hashlib
import hmac
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import quote_plus

Pairs = Sequence[tuple[str, str]]


def signature_base(
    pairs: Iterable[tuple[str, str]], passphrase: str = "", *, skip_blank: bool
) -> str:
    parts = []
    for key, value in pairs:
        value = value.strip()
        if skip_blank and value == "":
            continue
        parts.append(f"{key}={quote_plus(value)}")
    if passphrase:
        parts.append(f"passphrase={quote_plus(passphrase.strip())}")
    return "&".join(parts)


def sign(pairs: Iterable[tuple[str, str]], passphrase: str = "", *, skip_blank: bool = True) -> str:
    base = signature_base(pairs, passphrase, skip_blank=skip_blank)
    # MD5 is what PayFast uses; it's a checksum here, not password storage.
    return hashlib.md5(base.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckoutRequest:
    merchant_id: str
    merchant_key: str
    return_url: str
    cancel_url: str
    notify_url: str
    first_name: str
    last_name: str
    email: str
    reference: str
    amount_cents: int
    item_name: str


def checkout_fields(req: CheckoutRequest, passphrase: str = "") -> list[tuple[str, str]]:
    """The form fields to POST to PayFast, in PayFast's documented order, with the signature."""
    fields: list[tuple[str, str]] = [
        ("merchant_id", req.merchant_id),
        ("merchant_key", req.merchant_key),
        ("return_url", req.return_url),
        ("cancel_url", req.cancel_url),
        ("notify_url", req.notify_url),
        ("name_first", req.first_name),
        ("name_last", req.last_name),
        ("email_address", req.email),
        ("m_payment_id", req.reference),
        ("amount", cents_to_amount(req.amount_cents)),
        ("item_name", req.item_name[:100]),
    ]
    fields = [(k, v) for k, v in fields if v.strip() != ""]
    fields.append(("signature", sign(fields, passphrase)))
    return fields


def cents_to_amount(cents: int) -> str:
    """12345 -> '123.45', the format PayFast expects."""
    return f"{cents // 100}.{cents % 100:02d}"


def amount_to_cents(amount: str) -> int:
    """'123.45' -> 12345. Raises ValueError for anything that isn't a plain money amount."""
    text = amount.strip()
    whole, _, frac = text.partition(".")
    if not whole.isdigit() or (frac and (not frac.isdigit() or len(frac) > 2)):
        raise ValueError(f"not a money amount: {amount!r}")
    return int(whole) * 100 + int(frac.ljust(2, "0") or "0")


class InvalidNotification(Exception):
    """A PayFast notification failed a check, so it must not change any payment."""


@dataclass(frozen=True)
class Notification:
    merchant_id: str
    reference: str
    pf_payment_id: str
    payment_status: str
    amount_cents: int


def verify_notification(pairs: Pairs, *, merchant_id: str, passphrase: str = "") -> Notification:
    """Check a notification's signature and fields, and return its parsed contents.

    `pairs` must be the form fields exactly as PayFast sent them, in order.
    """
    data = dict(pairs)
    received = data.get("signature", "")
    signed_part: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == "signature":
            break
        signed_part.append((key, value))
    expected = sign(signed_part, passphrase, skip_blank=False)
    if not received or not hmac.compare_digest(expected, received.strip().lower()):
        raise InvalidNotification("signature does not match")

    if data.get("merchant_id", "").strip() != merchant_id:
        raise InvalidNotification("notification is for a different merchant")

    try:
        amount_cents = amount_to_cents(data.get("amount_gross", ""))
    except ValueError as exc:
        raise InvalidNotification("amount_gross is missing or malformed") from exc

    reference = data.get("m_payment_id", "").strip()
    pf_payment_id = data.get("pf_payment_id", "").strip()
    if not reference or not pf_payment_id:
        raise InvalidNotification("m_payment_id or pf_payment_id is missing")

    return Notification(
        merchant_id=merchant_id,
        reference=reference,
        pf_payment_id=pf_payment_id,
        payment_status=data.get("payment_status", "").strip().upper(),
        amount_cents=amount_cents,
    )
