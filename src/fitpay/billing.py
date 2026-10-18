"""Billing rules: how far a client has paid, and whether they're up to date.

These are plain functions with no database or web code, so they're easy to test.
"""

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ClientStatus(StrEnum):
    NOT_PAID = "not_paid"
    UP_TO_DATE = "up_to_date"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    FINISHED = "finished"


@dataclass(frozen=True)
class PaidPeriod:
    """One completed payment and the number of months it covers."""

    months: int


def add_months(start: date, months: int) -> date:
    """Move a date forward by whole months, keeping the day where possible.

    31 January + 1 month is 28 (or 29) February, because February has no 31st.
    """
    if months < 0:
        raise ValueError("months must not be negative")
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def paid_until(start_date: date, payments: Iterable[PaidPeriod]) -> date | None:
    """The date a client's paid-up cover runs out, or None if they've never paid.

    Each completed payment adds its months on top of the client's start date, so paying
    early or late never loses or gains a month.
    """
    total = sum(p.months for p in payments)
    if total == 0:
        return None
    return add_months(start_date, total)


def client_status(
    *,
    start_date: date,
    payments: Iterable[PaidPeriod],
    once_off: bool,
    today: date,
    due_soon_days: int,
) -> ClientStatus:
    until = paid_until(start_date, payments)
    if until is None:
        return ClientStatus.NOT_PAID
    days_left = (until - today).days
    if days_left < 0:
        # A once-off program that has run its course is finished, not overdue.
        return ClientStatus.FINISHED if once_off else ClientStatus.OVERDUE
    if days_left <= due_soon_days and not once_off:
        return ClientStatus.DUE_SOON
    return ClientStatus.UP_TO_DATE


def format_rands(cents: int) -> str:
    """1234567 -> 'R12 345.67' (South African style, with a space between thousands)."""
    sign = "-" if cents < 0 else ""
    rands, rest = divmod(abs(cents), 100)
    return f"{sign}R{rands:,}.{rest:02d}".replace(",", " ")
