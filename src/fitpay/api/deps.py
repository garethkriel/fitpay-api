"""Things routes ask FastAPI for: the database session, settings, today's date, admin access."""

import secrets
from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from fitpay.config import Settings
from fitpay.db import Database


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    db: Database = request.app.state.db
    yield from db.session()


def get_today() -> date:
    # A dependency so tests can pin "today" to a fixed date.
    return date.today()


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
TodayDep = Annotated[date, Depends(get_today)]


# Declared as a security scheme so the /docs page shows an "Authorize" button for it.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_admin(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Security(api_key_header)] = None,
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin API key is not configured")
    # compare_digest takes the same time whether the key is nearly right or totally wrong.
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or wrong X-API-Key header")


Admin = Depends(require_admin)
