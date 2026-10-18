from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from fitpay import __version__
from fitpay.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["health"])


@router.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    """Send visitors to the interactive API docs."""
    return RedirectResponse("/docs")


@router.get("/health")
def health(session: SessionDep, settings: SettingsDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "version": __version__,
        "payfast": "sandbox" if settings.payfast_sandbox else "live",
    }
