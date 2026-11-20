"""Настройка логирования.

Логи пишутся в stdout в формате JSON-строк (log-structured logging):
каждое событие — одна строка, удобная для сбора в ELK/Loki и для `docker logs`.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from .config import settings

#: Идентификатор текущего HTTP-запроса, доступный из любого слоя приложения.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

_RESERVED = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
        "relativeCreated", "thread", "threadName", "processName", "process", "taskName",
        "message", "asctime",
    }
)


class JsonFormatter(logging.Formatter):
    """Форматирует запись лога как одну JSON-строку."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id

        # любые дополнительные поля, переданные через logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Перенастраивает корневой логгер на вывод JSON в stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # uvicorn пишет собственные логи — у них должен быть тот же формат.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


configure_logging()
logger = logging.getLogger("app")
