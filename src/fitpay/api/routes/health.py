from fastapi import APIRouter
from sqlalchemy import text

from fitpay import __version__
from fitpay.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: SessionDep, settings: SettingsDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "version": __version__,
        "payfast": "sandbox" if settings.payfast_sandbox else "live",
    }
