from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from fitpay import payfast
from fitpay.api.deps import SessionDep, SettingsDep, TodayDep
from fitpay.services import apply_notification

router = APIRouter(tags=["payfast"])


@router.post("/payfast/notify", response_class=PlainTextResponse)
async def notify(
    request: Request, session: SessionDep, settings: SettingsDep, today: TodayDep
) -> str:
    """PayFast's Instant Transaction Notification (ITN).

    The body is read raw because the signature depends on the exact field order PayFast used.
    """
    body = (await request.body()).decode("utf-8")
    pairs = parse_qsl(body, keep_blank_values=True)
    note = payfast.verify_notification(
        pairs,
        merchant_id=settings.payfast_merchant_id,
        passphrase=settings.payfast_passphrase,
    )
    apply_notification(session, note, today=today)
    return "OK"
