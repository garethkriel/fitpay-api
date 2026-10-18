"""Demo data: five coaching packages and five made-up clients, one in each payment state."""

import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitpay.billing import add_months
from fitpay.models import Billing, Client, Package, Payment, PaymentMethod, PaymentStatus

PACKAGES = [
    ("Junior U18", "Online coaching for under-18s.", 50_000, Billing.MONTHLY, 1),
    ("Lifestyle Training", "Monthly plan and check-ins.", 100_000, Billing.MONTHLY, 1),
    ("Month-to-Month Program", "Full coaching, cancel any time.", 120_000, Billing.MONTHLY, 1),
    ("12 Week Transformation", "Three months of coaching.", 200_000, Billing.ONCE_OFF, 3),
    ("Once-Off Program", "A three-month program, paid up front.", 280_000, Billing.ONCE_OFF, 3),
]


def months_ago(today: date, months: int) -> date:
    index = today.month - 1 - months
    year, month = today.year + index // 12, index % 12 + 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def seed(session: Session, *, today: date) -> int:
    """Add the demo data if the database is empty. Returns how many clients were added."""
    if session.scalar(select(Package.id).limit(1)) is not None:
        return 0

    packages: dict[str, Package] = {}
    for name, description, cents, billing, months in PACKAGES:
        packages[name] = Package(
            name=name, description=description, price_cents=cents, billing=billing, months=months
        )
    session.add_all(packages.values())
    session.flush()

    lifestyle = packages["Lifestyle Training"]
    monthly = packages["Month-to-Month Program"]
    transformation = packages["12 Week Transformation"]

    # (name, email, package, start date, number of payments). One client per status:
    # up to date, overdue, not paid yet, finished (once-off program), due soon.
    clients = [
        ("Thandi Mokoena", "thandi@example.com", lifestyle, months_ago(today, 2), 3),
        ("Pieter van Wyk", "pieter@example.com", monthly, months_ago(today, 4), 2),
        ("Ayesha Patel", "ayesha@example.com", lifestyle, today - timedelta(days=10), 0),
        ("Lerato Dlamini", "lerato@example.com", transformation, months_ago(today, 5), 1),
        ("Johan Botha", "johan@example.com", monthly, today - timedelta(days=25), 1),
    ]
    for name, email, package, start, payments in clients:
        client = Client(name=name, email=email, package_id=package.id, start_date=start)
        session.add(client)
        session.flush()
        for i in range(payments):
            session.add(
                Payment(
                    client_id=client.id,
                    package_id=package.id,
                    amount_cents=package.price_cents,
                    months=package.months,
                    method=PaymentMethod.EFT if i % 2 else PaymentMethod.CASH,
                    status=PaymentStatus.COMPLETE,
                    paid_on=add_months(start, i * package.months),
                )
            )
    session.commit()
    return len(clients)
