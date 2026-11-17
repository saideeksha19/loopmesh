"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _engine_options() -> dict:
    options: dict = {"pool_pre_ping": True, "echo": settings.database_echo, "future": True}
    if settings.is_sqlite:
        # SQLite is a local development fallback only; it is not thread-bound
        # the way a server database is and needs a disable-able FK pragma.
        options["connect_args"] = {"check_same_thread": False}
    else:
        options["pool_size"] = settings.database_pool_size
        options["max_overflow"] = settings.database_pool_max_overflow
    return options


engine: Engine = create_engine(settings.database_url, **_engine_options())

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a transactional session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
