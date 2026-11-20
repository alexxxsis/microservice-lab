# syntax=docker/dockerfile:1.7
# =====================================================================
#  Multi-stage сборка микросервиса Task Tracker API.
#
#  Стадии:
#    builder  — установка python-зависимостей в отдельный venv;
#    test     — образ с dev-зависимостями для прогона pytest (docker build --target test);
#    runtime  — минимальный финальный образ (по умолчанию), только venv + код.
# =====================================================================
ARG PYTHON_VERSION=3.12

# ------------------------------------------------------------------ builder
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

# Зависимости ставятся в отдельный venv: его целиком копируем в runtime-образ.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ------------------------------------------------------------------ test
FROM python:${PYTHON_VERSION}-slim AS test

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=test

WORKDIR /app
COPY requirements.txt requirements-dev.txt pytest.ini ./
RUN pip install -r requirements-dev.txt
COPY app ./app
COPY tests ./tests

CMD ["python", "-m", "pytest", "-q"]

# ------------------------------------------------------------------ runtime
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="task-tracker-api" \
      org.opencontainers.image.description="RESTful-микросервис учёта задач (FastAPI + PostgreSQL)" \
      org.opencontainers.image.version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PORT=8080

# Непривилегированный пользователь: контейнер не работает от root.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app app ./app

USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "2", \
     "--no-access-log", \
     "--proxy-headers"]
