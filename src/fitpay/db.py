"""Database engine and sessions (SQLAlchemy 2.0)."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url in ("sqlite://", "sqlite:///:memory:"):
        # An in-memory database lives inside one connection, so every session must share it.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url.startswith("sqlite"):
        # FastAPI may use the session on a different thread from the one that opened it.
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


class Database:
    """Owns the engine and hands out sessions. One per app, so tests can use their own."""

    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_tables(self) -> None:
        # Importing the models registers them on Base.metadata.
        from fitpay import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def open(self) -> Session:
        """A new session, for use in a `with` block."""
        return self._sessions()

    def session(self) -> Iterator[Session]:
        """A session for one web request (used as a FastAPI dependency)."""
        with self.open() as session:
            yield session
