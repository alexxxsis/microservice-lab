"""Конфигурация микросервиса.

Все параметры читаются из переменных окружения, поэтому один и тот же образ
можно запускать в разных средах (docker-compose, CI, локальная отладка).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    """Настройки приложения (immutable, читаются один раз при старте)."""

    service_name: str = field(default_factory=lambda: _env("SERVICE_NAME", "task-tracker-api"))
    version: str = "1.0.0"
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "production"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO").upper())
    database_url: str = field(
        default_factory=lambda: _env(
            "DATABASE_URL",
            "postgresql+psycopg://task_user:task_pass@localhost:5432/taskdb",
        )
    )
    db_pool_size: int = field(default_factory=lambda: int(_env("DB_POOL_SIZE", "5")))
    db_max_overflow: int = field(default_factory=lambda: int(_env("DB_MAX_OVERFLOW", "10")))
    db_wait_seconds: int = field(default_factory=lambda: int(_env("DB_WAIT_SECONDS", "30")))
    docs_enabled: bool = field(default_factory=lambda: _env("DOCS_ENABLED", "true").lower() in {"1", "true", "yes"})


settings = Settings()
