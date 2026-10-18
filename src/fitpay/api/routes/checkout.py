from fastapi import APIRouter, status
from sqlalchemy import select

from fitpay.api.deps import SessionDep, SettingsDep, TodayDep
from fitpay.models import Payment
from fitpay.schemas import CheckoutIn, CheckoutOut
from fitpay.services import NotFound, start_checkout

router = APIRouter(tags=["checkout"])


@router.post("/checkout", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
def checkout(
    data: CheckoutIn, session: SessionDep, settings: SettingsDep, today: TodayDep
) -> CheckoutOut:
    """Start a PayFast payment for a package. No account needed: clients are matched by email."""
    return start_checkout(session, settings, data, today=today)


def _payment_state(session: SessionDep, reference: str) -> dict[str, str]:
    payment = session.scalar(select(Payment).where(Payment.reference == reference))
    if payment is None:
        raise NotFound("payment not found")
    return {"reference": payment.reference, "status": payment.status.value}


@router.get("/payments/{reference}/done")
def payment_done(reference: str, session: SessionDep) -> dict[str, str]:
    """Where PayFast sends the client after paying. The notification may arrive a moment later."""
    return _payment_state(session, reference)


@router.get("/payments/{reference}/cancelled")
def payment_cancelled(reference: str, session: SessionDep) -> dict[str, str]:
    return _payment_state(session, reference)
