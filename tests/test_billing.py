from datetime import date

import pytest

from fitpay.billing import (
    ClientStatus,
    PaidPeriod,
    add_months,
    client_status,
    format_rands,
    paid_until,
)


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 15), 1, date(2026, 2, 15)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),  # February has no 31st
        (date(2028, 1, 31), 1, date(2028, 2, 29)),  # leap year
        (date(2026, 11, 30), 3, date(2027, 2, 28)),  # crosses the year end
        (date(2026, 5, 10), 0, date(2026, 5, 10)),
        (date(2026, 5, 10), 24, date(2028, 5, 10)),
    ],
)
def test_add_months(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


def test_add_months_rejects_negative() -> None:
    with pytest.raises(ValueError):
        add_months(date(2026, 1, 1), -1)


def test_paid_until_adds_every_payment_to_the_start_date() -> None:
    start = date(2026, 1, 10)
    assert paid_until(start, []) is None
    assert paid_until(start, [PaidPeriod(1), PaidPeriod(1)]) == date(2026, 3, 10)
    assert paid_until(start, [PaidPeriod(3)]) == date(2026, 4, 10)


def status(payments: list[int], *, today: date, once_off: bool = False) -> ClientStatus:
    return client_status(
        start_date=date(2026, 1, 10),
        payments=[PaidPeriod(m) for m in payments],
        once_off=once_off,
        today=today,
        due_soon_days=7,
    )


def test_status_not_paid() -> None:
    assert status([], today=date(2026, 1, 10)) is ClientStatus.NOT_PAID


def test_status_up_to_date_due_soon_and_overdue() -> None:
    # Paid one month: covered until 10 February.
    assert status([1], today=date(2026, 1, 20)) is ClientStatus.UP_TO_DATE
    assert status([1], today=date(2026, 2, 3)) is ClientStatus.DUE_SOON  # 7 days left
    assert status([1], today=date(2026, 2, 10)) is ClientStatus.DUE_SOON  # last day
    assert status([1], today=date(2026, 2, 11)) is ClientStatus.OVERDUE


def test_once_off_program_finishes_instead_of_going_overdue() -> None:
    assert status([3], today=date(2026, 4, 5), once_off=True) is ClientStatus.UP_TO_DATE
    assert status([3], today=date(2026, 4, 11), once_off=True) is ClientStatus.FINISHED


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "R0.00"),
        (5, "R0.05"),
        (120_000, "R1 200.00"),
        (123_456_789, "R1 234 567.89"),
        (-250, "-R2.50"),
    ],
)
def test_format_rands(cents: int, text: str) -> None:
    assert format_rands(cents) == text
