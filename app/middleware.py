"""Middleware: идентификатор запроса и журнал доступа."""

from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .errors import error_response
from .logging_conf import logger, request_id_ctx

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _request_id_from_header(request: Request) -> str:
    """Берём X-Request-ID от клиента (например, из Postman), если он корректен."""
    candidate = request.headers.get("X-Request-ID", "")
    if candidate and _REQUEST_ID_RE.match(candidate):
        return candidate
    return uuid.uuid4().hex[:12]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Проставляет request_id, измеряет длительность и логирует каждый запрос."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _request_id_from_header(request)
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - последний рубеж: сервис не должен падать
            logger.exception(
                "unhandled_exception",
                extra={"event": "unhandled_exception", "method": request.method, "path": request.url.path},
            )
            response = error_response(
                500,
                "INTERNAL_ERROR",
                "Внутренняя ошибка сервиса. Попробуйте позже или обратитесь к администратору.",
            )
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.2f}"

        log = logger.warning if response.status_code >= 500 else logger.info
        log(
            "http_request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query or None,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else None,
            },
        )

        request_id_ctx.reset(token)
        return response
