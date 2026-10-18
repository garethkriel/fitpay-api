"""Builds the FastAPI app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from fitpay import __version__
from fitpay.api.routes import checkout, clients, health, packages, payfast_notify, reports
from fitpay.config import Settings, get_settings
from fitpay.db import Database
from fitpay.payfast import InvalidNotification
from fitpay.seed import seed
from fitpay.services import Conflict, NotFound


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.create_tables()
        if settings.demo:
            with db.open() as session:
                seed(session, today=date.today())
        yield
        db.engine.dispose()

    app = FastAPI(
        title="FitPay API",
        version=__version__,
        description="Clients, packages and PayFast payments for coaching businesses.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)

    @app.exception_handler(InvalidNotification)
    async def bad_notification(_: Request, exc: InvalidNotification) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)

    for module in (health, packages, clients, checkout, payfast_notify, reports):
        app.include_router(module.router)
    return app
