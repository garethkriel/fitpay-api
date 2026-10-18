from datetime import date

from typer.testing import CliRunner

from fitpay import cli
from fitpay.billing import ClientStatus
from fitpay.config import Settings, get_settings
from fitpay.db import Database
from fitpay.seed import seed
from fitpay.services import list_clients

TODAY = date(2026, 10, 18)


def test_seed_creates_one_client_in_each_state() -> None:
    db = Database("sqlite://")
    db.create_tables()
    with db.open() as session:
        assert seed(session, today=TODAY) == 5
        assert seed(session, today=TODAY) == 0  # only fills an empty database
        rows = list_clients(session, today=TODAY, settings=Settings(database_url="sqlite://"))
    assert sorted(r.status for r in rows) == sorted(ClientStatus)


def test_cli_seed_and_overdue(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FITPAY_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    get_settings.cache_clear()
    runner = CliRunner()
    try:
        first = runner.invoke(cli.app, ["seed"])
        assert first.exit_code == 0, first.output
        assert "Added 5 packages and 5 demo clients" in first.output

        again = runner.invoke(cli.app, ["seed"])
        assert "nothing was added" in again.output

        overdue = runner.invoke(cli.app, ["overdue"])
        assert overdue.exit_code == 0
        assert "Pieter van Wyk" in overdue.output
    finally:
        get_settings.cache_clear()
