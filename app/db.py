"""Работа с СУБД PostgreSQL: движок SQLAlchemy, сессии, ожидание готовности БД."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .logging_conf import logger

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: сессия БД на время одного запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> dict[str, Any]:
    """Проверяет доступность БД. Возвращает описание версии сервера."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version() AS version, current_database() AS db")).one()
    return {"database": row.db, "server_version": str(row.version).split(",")[0]}


def wait_for_database(max_wait_seconds: int | None = None, delay: float = 1.0) -> bool:
    """Ждёт, пока БД станет доступна (контейнер с postgres может стартовать дольше).

    Возвращает True, если соединение установлено. Сервис при этом не падает:
    пока БД недоступна, API отвечает 503 на запросы к данным.
    """
    deadline = time.monotonic() + (max_wait_seconds if max_wait_seconds is not None else settings.db_wait_seconds)
    attempt = 0
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        attempt += 1
        try:
            info = check_database()
            logger.info(
                "database_connection_established",
                extra={"event": "db_connected", "attempt": attempt, **info},
            )
            return True
        except SQLAlchemyError as exc:
            last_error = exc
            logger.warning(
                "database_not_ready",
                extra={"event": "db_retry", "attempt": attempt, "error": type(exc).__name__},
            )
            time.sleep(delay)

    logger.error(
        "database_unavailable",
        extra={"event": "db_unavailable", "attempts": attempt, "error": str(last_error)},
    )
    return False
