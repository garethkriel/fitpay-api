"""Command line: `fitpay serve`, `fitpay seed`, `fitpay overdue`."""

from datetime import date

import typer

from fitpay.billing import ClientStatus
from fitpay.config import get_settings
from fitpay.db import Database
from fitpay.seed import seed as seed_demo
from fitpay.services import list_clients

app = typer.Typer(help="FitPay: clients, packages and PayFast payments.", no_args_is_help=True)


def _database() -> Database:
    db = Database(get_settings().database_url)
    db.create_tables()
    return db


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Run the API. Open http://127.0.0.1:8000/docs to try it in the browser."""
    import uvicorn

    uvicorn.run("fitpay.main:app", host=host, port=port, reload=reload)


@app.command()
def seed() -> None:
    """Fill an empty database with demo packages and clients."""
    with _database().open() as session:
        added = seed_demo(session, today=date.today())
    if added:
        typer.echo(f"Added 5 packages and {added} demo clients.")
    else:
        typer.echo("The database already has data, so nothing was added.")


@app.command()
def overdue() -> None:
    """List clients whose payments are overdue."""
    with _database().open() as session:
        rows = list_clients(
            session, today=date.today(), settings=get_settings(), status=ClientStatus.OVERDUE
        )
    if not rows:
        typer.echo("Nobody is overdue.")
        return
    for row in rows:
        typer.echo(f"{row.name:<25} {row.email:<30} paid until {row.paid_until}")


if __name__ == "__main__":
    app()
