"""Entry point for ASGI servers: `uvicorn fitpay.main:app`."""

from fitpay.api.app import create_app

app = create_app()
