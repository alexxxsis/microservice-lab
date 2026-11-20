# Task Tracker API — лабораторная работа «Разработка микросервиса»

RESTful-микросервис учёта задач (task tracker) на **Python / FastAPI** с реляционной СУБД
**PostgreSQL**. Микросервис и СУБД разворачиваются совместно через **docker compose**,
образ собирается **multi-stage** `Dockerfile`.

## Что реализовано по требованиям

| Требование | Где реализовано |
|---|---|
| Минимум 4 запроса REST | 7 эндпоинтов: `POST`, `GET` (список), `GET` (по id), `PATCH`, `DELETE`, `GET /stats`, `GET /health` |
| Любой язык | Python 3.12, FastAPI, SQLAlchemy 2.0, psycopg 3 |
| Реляционная СУБД | PostgreSQL 16 (таблица `tasks`, индексы, CHECK-ограничения, триггер `updated_at`) |
| Совместное развёртывание в контейнерах | `docker-compose.yml`: сервисы `api` и `db`, общая сеть `task-tracker-net`, том `task-tracker-pgdata` |
| docker compose + multi-stage | `docker-compose.yml` + `Dockerfile` со стадиями `builder → test → runtime` |
| Git | репозиторий на GitHub (см. ссылку в отчёте) |
| Проверка через Postman | `postman/task-tracker.postman_collection.json` + окружение, прогон в CI через Newman |
| Обработка ошибок | единый JSON-формат, коды `400 / 404 / 409 / 422 / 503`, сервис не падает |
| Логирование (опционально) | JSON-логи в stdout: каждый запрос, `request_id`, длительность, ошибки с traceback |
| Swagger (опционально) | `http://localhost:8080/docs`, `http://localhost:8080/redoc`, схема `/openapi.json` |

## Структура проекта

```
.
├── Dockerfile                  # multi-stage: builder → test → runtime
├── docker-compose.yml          # api + db, healthcheck, тома, сеть
├── requirements.txt            # runtime-зависимости (фиксированные версии)
├── requirements-dev.txt        # pytest/httpx для тестов
├── .env.example                # параметры окружения для compose
├── app/
│   ├── main.py                 # создание FastAPI, lifespan, роутеры
│   ├── config.py               # настройки из переменных окружения
│   ├── db.py                   # движок SQLAlchemy, сессии, ожидание БД
│   ├── models.py               # ORM-модель Task, статусы и приоритеты
│   ├── schemas.py              # Pydantic-схемы запросов/ответов
│   ├── errors.py               # единый формат ошибок и HTTP-коды
│   ├── middleware.py           # request_id, журнал доступа, перехват 500
│   ├── logging_conf.py         # JSON-логирование в stdout
│   └── routers/
│       ├── health.py            # /health, /health/live
│       └── tasks.py             # CRUD, фильтры, статистика
├── db/init/                    # SQL-скрипты, выполняемые при инициализации БД
│   ├── 01_schema.sql
│   └── 02_seed.sql
├── tests/test_api.py           # интеграционные тесты (pytest)
├── postman/                    # коллекция и окружение Postman
├── scripts/                    # генератор коллекции Postman
├── .github/workflows/ci.yml    # сборка compose + Newman + pytest в CI
└── docs/                       # скриншоты и материалы отчёта
```

## Быстрый старт

```bash
git clone <URL репозитория> && cd microservice-lab

# при необходимости изменить порты/пароли
cp .env.example .env

docker compose up -d --build      # соберёт образ и поднимет api + db
docker compose ps                 # оба сервиса healthy
docker compose logs -f api        # JSON-логи в реальном времени
```

Сервис доступен на `http://localhost:8080`:

* `GET /docs` — Swagger UI;
* `GET /health` — проверка готовности (включая БД);
* `GET /api/v1/tasks` — список задач (в БД уже есть демо-данные из `db/init/02_seed.sql`).

Остановка:

```bash
docker compose down        # контейнеры и сеть, данные сохраняются в томе
docker compose down -v     # вместе с томом (БД пересоздастся при следующем старте)
```

## Эндпоинты

| Метод | Путь | Назначение | Успех | Ошибки |
|---|---|---|---|---|
| `GET` | `/health/live` | живость процесса | `200` | — |
| `GET` | `/health` | готовность + соединение с БД | `200` | `503` |
| `GET` | `/api/v1/tasks` | список с фильтрами `status`, `priority`, `search`, `limit`, `offset` | `200` | `422` |
| `GET` | `/api/v1/tasks/{id}` | задача по идентификатору | `200` | `404`, `422` |
| `POST` | `/api/v1/tasks` | создание задачи | `201` + `Location` | `409`, `422` |
| `PATCH` | `/api/v1/tasks/{id}` | частичное обновление | `200` | `404`, `409`, `422` |
| `DELETE` | `/api/v1/tasks/{id}` | удаление задачи | `204` | `404`, `422` |
| `GET` | `/api/v1/tasks/stats` | агрегаты по статусу/приоритету, просроченные | `200` | `503` |

### Примеры запросов

```bash
# создание
curl -i -X POST http://localhost:8080/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: demo-1" \
  -d '{"title":"Подготовить отчёт","description":"ЛР по микросервисам","priority":"high","due_date":"2026-12-01"}'

# список с фильтрами
curl "http://localhost:8080/api/v1/tasks?status=todo&priority=high&limit=10&offset=0"

# частичное обновление
curl -X PATCH http://localhost:8080/api/v1/tasks/1 \
  -H "Content-Type: application/json" -d '{"status":"done"}'

# удаление
curl -i -X DELETE http://localhost:8080/api/v1/tasks/1

# статистика
curl http://localhost:8080/api/v1/tasks/stats
```

## Формат ошибок

Все ошибки возвращаются в одном виде, поэтому клиенту не нужно разбирать разные форматы:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Некорректные данные в запросе",
    "details": [
      { "field": "title", "message": "String should have at least 3 characters", "type": "string_too_short" }
    ]
  },
  "request_id": "9f3c1a7b2d4e"
}
```

| Код | `error.code` | Когда возникает |
|---|---|---|
| `400` | `INVALID_JSON` | тело запроса — синтаксически битый JSON |
| `404` | `TASK_NOT_FOUND` / `NOT_FOUND` | задачи/ресурса нет |
| `405` | `METHOD_NOT_ALLOWED` | метод не поддерживается для пути |
| `409` | `CONFLICT` | задача с таким названием уже существует (UNIQUE) |
| `422` | `VALIDATION_ERROR` | не прошла валидация полей/параметров (в т.ч. неизвестное поле) |
| `500` | `INTERNAL_ERROR` | непредвиденная ошибка (в лог пишется traceback, клиенту — без деталей) |
| `503` | `DATABASE_UNAVAILABLE` | БД недоступна — сервис продолжает работать и отвечает 503 |

Дополнительно в каждом ответе есть заголовки `X-Request-ID` и `X-Response-Time-ms`:
по `request_id` можно найти все строки лога, относящиеся к конкретному запросу.

## Логирование

Каждое событие — одна JSON-строка в stdout (`docker logs task-tracker-api`):

```json
{"ts":"2026-11-20T18:12:04.512+00:00","level":"INFO","logger":"app","message":"http_request","request_id":"demo-1","event":"http_request","method":"POST","path":"/api/v1/tasks","status":201,"duration_ms":12.41,"client":"172.18.0.1"}
```

Логируются: старт/остановка сервиса, ожидание БД, каждый HTTP-запрос (метод, путь, статус,
длительность), бизнес-события (`task_created`, `task_updated`, `task_deleted`) и все ошибки —
включая `traceback` для необработанных исключений.

## Postman

В каталоге `postman/`:

* `task-tracker.postman_collection.json` — 23 запроса в 3 папках (служебные, CRUD, ошибки);
  переменная `baseUrl` = `http://localhost:8080`, `taskId` заполняется автоматически из ответа;
* `task-tracker.postman_environment.json` — окружение «Task Tracker Local».

Импорт: Postman → **Import** → выбрать оба файла → выбрать окружение → **Send**.
Те же запросы прогоняются в CI через Newman:

```bash
npx newman run postman/task-tracker.postman_collection.json \
  -e postman/task-tracker.postman_environment.json
```

## Тесты

```bash
# в контейнере (стадия test)
docker build --target test -t task-tracker-api:test .
docker run --rm --network task-tracker-net \
  -e DATABASE_URL=postgresql+psycopg://task_user:task_pass@db:5432/taskdb \
  task-tracker-api:test

# локально (нужен доступный PostgreSQL со схемой из db/init)
pip install -r requirements-dev.txt
DATABASE_URL=postgresql+psycopg://task_user:task_pass@localhost:5433/taskdb pytest -q
```

## CI

`.github/workflows/ci.yml` на каждый push: проверяет `docker compose config`, собирает
multi-stage образ, поднимает `api` + `db`, ждёт health-check, прогоняет `pytest` в стадии
`test`, прогоняет Postman-коллекцию через Newman, выгружает отчёты артефактами и показывает
логи контейнеров.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://task_user:task_pass@localhost:5432/taskdb` | строка подключения к PostgreSQL |
| `APP_ENV` | `production` | окружение (в ответах `/health`) |
| `LOG_LEVEL` | `INFO` | уровень логирования |
| `DB_WAIT_SECONDS` | `30` | сколько секунд ждать БД при старте |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `10` | параметры пула соединений |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `taskdb` / `task_user` / `task_pass` | параметры СУБД для compose |
| `API_PORT` / `POSTGRES_PORT` | `8080` / `5433` | порты на хосте |
