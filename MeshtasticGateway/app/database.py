"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = None
SessionLocal = None


def _bind_engine(url: str) -> None:
    global engine, SessionLocal
    engine = create_engine(url, **_engine_kwargs(url))

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        if url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


_bind_engine(settings.database_url)


def reset_engine(url: str | None = None) -> None:
    """Used by tests to point at a temporary SQLite file."""
    if url:
        settings.database_url = url
    _bind_engine(settings.database_url)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401 — register tables

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    (settings.log_dir.parent / "database").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
