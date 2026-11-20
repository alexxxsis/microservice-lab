"""Точка входа микросервиса Task Tracker API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .config import settings
from .db import engine, wait_for_database
from .errors import register_exception_handlers
from .logging_conf import logger
from .middleware import RequestContextMiddleware
from .routers import health, tasks

DESCRIPTION = """
Микросервис учёта задач (task tracker) с RESTful API и реляционной СУБД PostgreSQL.

**Возможности**

* CRUD-операции над задачами (`POST`, `GET`, `PATCH`, `DELETE`);
* фильтрация, поиск и постраничная выдача списка задач;
* агрегированная статистика (считается в PostgreSQL);
* единый формат ошибок, корректные HTTP-коды, логирование в JSON.

Полная интерактивная документация — на этой странице (`Swagger UI`), схема OpenAPI — `/openapi.json`.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "service_starting",
        extra={
            "event": "startup",
            "service": settings.service_name,
            "version": settings.version,
            "environment": settings.app_env,
        },
    )
    # Ждём БД в отдельном потоке, чтобы не блокировать event loop.
    ready = await asyncio.to_thread(wait_for_database)
    logger.info(
        "service_ready" if ready else "service_started_without_database",
        extra={"event": "startup_done", "database_ready": ready},
    )
    yield
    engine.dispose()
    logger.info("service_stopped", extra={"event": "shutdown"})


app = FastAPI(
    title="Task Tracker API",
    version=settings.version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "Лабораторная работа: разработка микросервиса"},
    openapi_tags=[
        {"name": "Задачи", "description": "Операции над задачами"},
        {"name": "Служебные", "description": "Health-check эндпоинты"},
    ],
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(tasks.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Корень: переадресует на интерактивную документацию."""
    return RedirectResponse(url="/docs")
