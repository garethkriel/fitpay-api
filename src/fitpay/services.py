"""Business logic that sits between the API routes and the database."""

import csv
import io
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fitpay import payfast
from fitpay.billing import ClientStatus, PaidPeriod, client_status, paid_until
from fitpay.config import Settings
from fitpay.models import Billing, Client, Package, Payment, PaymentMethod, PaymentStatus
from fitpay.schemas import (
    CheckoutIn,
    CheckoutOut,
    ClientDetail,
    ClientSummary,
    ManualPaymentIn,
    MonthRevenue,
    PaymentOut,
)


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


# --- Clients ----------------------------------------------------------------


def _periods(client: Client) -> list[PaidPeriod]:
    return [PaidPeriod(p.months) for p in client.payments if p.status == PaymentStatus.COMPLETE]


def summarize(client: Client, *, today: date, settings: Settings) -> ClientSummary:
    periods = _periods(client)
    once_off = client.package is not None and client.package.billing == Billing.ONCE_OFF
    return ClientSummary(
        id=client.id,
        name=client.name,
        email=client.email,
        package=client.package.name if client.package else None,
        status=client_status(
            start_date=client.start_date,
            payments=periods,
            once_off=once_off,
            today=today,
            due_soon_days=settings.due_soon_days,
        ),
        paid_until=paid_until(client.start_date, periods),
        archived=client.archived,
    )


def detail(client: Client, *, today: date, settings: Settings) -> ClientDetail:
    summary = summarize(client, today=today, settings=settings)
    return ClientDetail(
        **summary.model_dump(),
        phone=client.phone,
        start_date=client.start_date,
        notes=client.notes,
        payments=[PaymentOut.model_validate(p) for p in client.payments],
    )


# Clients who owe money come first, then those due soon, and so on.
STATUS_ORDER = {
    ClientStatus.OVERDUE: 0,
    ClientStatus.NOT_PAID: 1,
    ClientStatus.DUE_SOON: 2,
    ClientStatus.UP_TO_DATE: 3,
    ClientStatus.FINISHED: 4,
}


def list_clients(
    session: Session,
    *,
    today: date,
    settings: Settings,
    status: ClientStatus | None = None,
    search: str | None = None,
    include_archived: bool = False,
) -> list[ClientSummary]:
    query = select(Client)
    if not include_archived:
        query = query.where(Client.archived.is_(False))
    if search:
        like = f"%{search.strip().lower()}%"
        query = query.where(
            func.lower(Client.name).like(like) | func.lower(Client.email).like(like)
        )
    clients = session.scalars(query).unique().all()
    summaries = [summarize(c, today=today, settings=settings) for c in clients]
    if status is not None:
        summaries = [s for s in summaries if s.status == status]
    return sorted(summaries, key=lambda s: (STATUS_ORDER[s.status], s.name.lower()))


def get_client(session: Session, client_id: int) -> Client:
    client = session.get(Client, client_id)
    if client is None:
        raise NotFound(f"client {client_id} not found")
    return client


def get_package(session: Session, package_id: int) -> Package:
    package = session.get(Package, package_id)
    if package is None:
        raise NotFound(f"package {package_id} not found")
    return package


def email_taken(session: Session, email: str, *, except_id: int | None = None) -> bool:
    query = select(Client.id).where(func.lower(Client.email) == email.lower())
    if except_id is not None:
        query = query.where(Client.id != except_id)
    return session.scalar(query) is not None


# --- Payments ---------------------------------------------------------------


def record_manual_payment(session: Session, client: Client, data: ManualPaymentIn) -> Payment:
    if data.method == PaymentMethod.PAYFAST:
        raise Conflict("PayFast payments are recorded automatically from PayFast's notification")
    if data.package_id is not None:
        get_package(session, data.package_id)
    payment = Payment(
        client_id=client.id,
        package_id=data.package_id or client.package_id,
        amount_cents=data.amount_cents,
        months=data.months,
        method=data.method,
        status=PaymentStatus.COMPLETE,
        paid_on=data.paid_on,
    )
    session.add(payment)
    session.commit()
    session.refresh(client)
    return payment


def start_checkout(
    session: Session, settings: Settings, data: CheckoutIn, *, today: date
) -> CheckoutOut:
    """Create (or reuse) the client and a pending payment, then build PayFast's form."""
    package = get_package(session, data.package_id)
    if not package.active:
        raise Conflict("that package is no longer available")

    client = session.scalar(select(Client).where(func.lower(Client.email) == data.email.lower()))
    if client is None:
        client = Client(
            name=f"{data.first_name} {data.last_name}",
            email=data.email.lower(),
            phone=data.phone,
            package_id=package.id,
            start_date=today,
        )
        session.add(client)
        session.flush()
    elif client.archived:
        client.archived = False

    payment = Payment(
        client_id=client.id,
        package_id=package.id,
        amount_cents=package.price_cents,
        months=package.months,
        method=PaymentMethod.PAYFAST,
        status=PaymentStatus.PENDING,
    )
    session.add(payment)
    session.commit()

    base = settings.public_url.rstrip("/")
    fields = payfast.checkout_fields(
        payfast.CheckoutRequest(
            merchant_id=settings.payfast_merchant_id,
            merchant_key=settings.payfast_merchant_key,
            return_url=f"{base}/payments/{payment.reference}/done",
            cancel_url=f"{base}/payments/{payment.reference}/cancelled",
            notify_url=f"{base}/payfast/notify",
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            reference=payment.reference,
            amount_cents=payment.amount_cents,
            item_name=package.name,
        ),
        settings.payfast_passphrase,
    )
    return CheckoutOut(
        action_url=settings.payfast_process_url,
        reference=payment.reference,
        fields=dict(fields),
    )


def apply_notification(session: Session, note: payfast.Notification, *, today: date) -> Payment:
    """Update a pending payment from a verified PayFast notification.

    Safe to call twice with the same notification: PayFast retries until it gets a 200.
    """
    payment = session.scalar(select(Payment).where(Payment.reference == note.reference))
    if payment is None:
        raise NotFound(f"no payment with reference {note.reference}")
    if payment.amount_cents != note.amount_cents:
        raise payfast.InvalidNotification(
            f"amount {note.amount_cents} does not match expected {payment.amount_cents}"
        )
    if payment.status == PaymentStatus.COMPLETE:
        if payment.pf_payment_id not in (None, note.pf_payment_id):
            raise Conflict("payment was already completed by a different PayFast payment")
        return payment

    if note.payment_status == "COMPLETE":
        payment.status = PaymentStatus.COMPLETE
        payment.pf_payment_id = note.pf_payment_id
        payment.paid_on = today
    elif note.payment_status == "CANCELLED":
        payment.status = PaymentStatus.CANCELLED
    else:
        payment.status = PaymentStatus.FAILED
    session.commit()
    return payment


# --- Reports ----------------------------------------------------------------


def _completed(session: Session) -> list[Payment]:
    query = (
        select(Payment)
        .where(Payment.status == PaymentStatus.COMPLETE, Payment.paid_on.is_not(None))
        .order_by(Payment.paid_on, Payment.id)
    )
    return list(session.scalars(query).all())


def revenue_by_month(session: Session, *, year: int | None = None) -> list[MonthRevenue]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for p in _completed(session):
        assert p.paid_on is not None
        if year is not None and p.paid_on.year != year:
            continue
        bucket = totals[p.paid_on.strftime("%Y-%m")]
        bucket[0] += 1
        bucket[1] += p.amount_cents
    return [
        MonthRevenue(month=month, payments=count, total_cents=cents)
        for month, (count, cents) in sorted(totals.items())
    ]


def payments_csv(session: Session) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["paid_on", "client", "email", "amount", "months", "method", "reference"])
    for p in _completed(session):
        assert p.paid_on is not None
        writer.writerow(
            [
                p.paid_on.isoformat(),
                p.client.name,
                p.client.email,
                payfast.cents_to_amount(p.amount_cents),
                p.months,
                p.method.value,
                p.reference,
            ]
        )
    return out.getvalue()
