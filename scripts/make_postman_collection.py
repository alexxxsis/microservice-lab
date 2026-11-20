"""Генератор Postman-коллекции и окружения для Task Tracker API.

Коллекция поддерживается в виде кода, чтобы она не расходилась с API:
    python scripts/make_postman_collection.py

Результат:
    postman/task-tracker.postman_collection.json
    postman/task-tracker.postman_environment.json
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
POSTMAN_DIR = ROOT / "postman"
BASE_URL = "http://localhost:8080"


def _url(path: str, query: list[tuple[str, str]] | None = None) -> dict:
    """Собирает объект url в формате Postman collection v2.1."""
    raw = "{{baseUrl}}" + path
    if query:
        raw += "?" + "&".join(f"{k}={v}" for k, v in query)
    return {
        "raw": raw,
        "host": ["{{baseUrl}}"],
        "path": [part for part in path.strip("/").split("/") if part],
        **({"query": [{"key": k, "value": v} for k, v in query]} if query else {}),
    }


def _json_body(payload: dict | str) -> dict:
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}


def _item(
    name: str,
    method: str,
    path: str,
    *,
    description: str = "",
    query: list[tuple[str, str]] | None = None,
    body: dict | str | None = None,
    prerequest: list[str] | None = None,
    tests: list[str] | None = None,
) -> dict:
    request: dict = {
        "method": method,
        "header": ([{"key": "Content-Type", "value": "application/json"}] if body is not None else []),
        "url": _url(path, query),
        "description": description,
    }
    if body is not None:
        request["body"] = _json_body(body)

    item: dict = {"name": name, "request": request, "response": []}
    events = []
    if prerequest:
        events.append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": prerequest}})
    if tests:
        events.append({"listen": "test", "script": {"type": "text/javascript", "exec": tests}})
    if events:
        item["event"] = events
    return item


# --------------------------------------------------------------------------- тесты
def status_is(code: int) -> list[str]:
    return [
        f"pm.test('HTTP-код {code}', function () {{",
        f"    pm.response.to.have.status({code});",
        "});",
    ]


def json_field(path: str, expected: object) -> list[str]:
    """Проверка значения поля в JSON-ответе (path вида ``body.status``)."""
    return [
        f"pm.test('Поле {path}', function () {{",
        "    const body = pm.response.json();",
        f"    pm.expect({path}).to.eql({json.dumps(expected, ensure_ascii=False)});",
        "});",
    ]


def error_code(code: str) -> list[str]:
    return [
        f"pm.test('Код ошибки {code}', function () {{",
        f"    pm.expect(pm.response.json().error.code).to.eql('{code}');",
        "});",
        "pm.test('Есть сопроводительное сообщение', function () {",
        "    pm.expect(pm.response.json().error.message).to.be.a('string').and.not.empty;",
        "});",
    ]


# --------------------------------------------------------------------------- запросы
service_items = [
    _item(
        "01 · Проверка живости (health/live)",
        "GET",
        "/health/live",
        description="Процесс сервиса запущен (используется в Docker HEALTHCHECK).",
        tests=status_is(200) + json_field("body.status", "ok") + json_field("body.service", "task-tracker-api"),
    ),
    _item(
        "02 · Проверка готовности (health + БД)",
        "GET",
        "/health",
        description="Сервис отвечает и соединение с PostgreSQL установлено.",
        tests=status_is(200) + json_field("body.database", "taskdb") + [
            "pm.test('Версия сервера PostgreSQL', function () {",
            "    pm.expect(pm.response.json().server_version).to.include('PostgreSQL');",
            "});",
        ],
    ),
    _item(
        "03 · Swagger UI",
        "GET",
        "/docs",
        description="Интерактивная документация Swagger (опциональное требование).",
        tests=status_is(200) + [
            "pm.test('Отдаётся HTML Swagger UI', function () {",
            "    pm.expect(pm.response.text()).to.include('swagger');",
            "});",
        ],
    ),
    _item(
        "04 · Схема OpenAPI",
        "GET",
        "/openapi.json",
        description="Машиночитаемое описание API.",
        tests=status_is(200) + [
            "pm.test('В схеме есть CRUD-пути', function () {",
            "    const paths = Object.keys(pm.response.json().paths);",
            "    pm.expect(paths).to.include('/api/v1/tasks');",
            "    pm.expect(paths).to.include('/api/v1/tasks/{task_id}');",
            "});",
        ],
    ),
]

crud_items = [
    _item(
        "05 · Создать задачу (POST)",
        "POST",
        "/api/v1/tasks",
        description="Создание задачи. Название уникально, поэтому в тело подставляется динамическая переменная {{$timestamp}}.",
        body={
            "title": "Задача из Postman {{$timestamp}}",
            "description": "Создано из коллекции Postman",
            "status": "todo",
            "priority": "high",
            "due_date": "2026-12-31",
        },
        tests=status_is(201) + [
            "const body = pm.response.json();",
            "pm.collectionVariables.set('taskId', body.id);",
            "pm.test('Ответ содержит id и статус todo', function () {",
            "    pm.expect(body.id).to.be.a('number');",
            "    pm.expect(body.status).to.eql('todo');",
            "    pm.expect(body.priority).to.eql('high');",
            "});",
            "pm.test('Заголовок Location указывает на созданный ресурс', function () {",
            "    pm.expect(pm.response.headers.get('Location')).to.eql('/api/v1/tasks/' + body.id);",
            "});",
            "pm.test('Вернулся request_id', function () {",
            "    pm.expect(pm.response.headers.get('X-Request-ID')).to.be.a('string');",
            "});",
        ],
    ),
    _item(
        "06 · Получить задачу по id (GET)",
        "GET",
        "/api/v1/tasks/{{taskId}}",
        description="Чтение созданной задачи.",
        tests=status_is(200) + [
            "const body = pm.response.json();",
            "pm.test('id совпадает с созданным', function () {",
            "    pm.expect(String(body.id)).to.eql(pm.collectionVariables.get('taskId'));",
            "});",
            "pm.test('Название не пустое', function () {",
            "    pm.expect(body.title).to.be.a('string').and.not.empty;",
            "});",
        ],
    ),
    _item(
        "07 · Список задач с фильтрами (GET)",
        "GET",
        "/api/v1/tasks",
        description="Постраничная выдача с фильтрами и поиском.",
        query=[("status", "todo"), ("priority", "high"), ("limit", "5"), ("offset", "0")],
        tests=status_is(200) + [
            "const body = pm.response.json();",
            "pm.test('Постраничный ответ', function () {",
            "    pm.expect(body.items).to.be.an('array');",
            "    pm.expect(body.limit).to.eql(5);",
            "    pm.expect(body.offset).to.eql(0);",
            "    pm.expect(body.total).to.be.a('number');",
            "});",
            "pm.test('Все задачи соответствуют фильтру', function () {",
            "    body.items.forEach((task) => {",
            "        pm.expect(task.status).to.eql('todo');",
            "        pm.expect(task.priority).to.eql('high');",
            "    });",
            "});",
        ],
    ),
    _item(
        "08 · Поиск по названию (GET)",
        "GET",
        "/api/v1/tasks",
        description="Фильтр search ищет подстроку в названии (ILIKE).",
        query=[("search", "Postman"), ("limit", "10")],
        tests=status_is(200) + [
            "pm.test('Найденные задачи содержат искомую подстроку', function () {",
            "    pm.response.json().items.forEach((task) => {",
            "        pm.expect(task.title.toLowerCase()).to.include('postman');",
            "    });",
            "});",
        ],
    ),
    _item(
        "09 · Частично обновить задачу (PATCH)",
        "PATCH",
        "/api/v1/tasks/{{taskId}}",
        description="Меняем только статус и приоритет, остальные поля сохраняются.",
        body={"status": "done", "priority": "medium"},
        tests=status_is(200) + [
            "const body = pm.response.json();",
            "pm.test('Статус изменился на done', function () {",
            "    pm.expect(body.status).to.eql('done');",
            "});",
            "pm.test('Описание не потерялось при частичном обновлении', function () {",
            "    pm.expect(body.description).to.eql('Создано из коллекции Postman');",
            "});",
            "pm.test('updated_at обновился', function () {",
            "    pm.expect(new Date(body.updated_at).getTime()).to.be.at.least(new Date(body.created_at).getTime());",
            "});",
        ],
    ),
    _item(
        "10 · Статистика по задачам (GET /stats)",
        "GET",
        "/api/v1/tasks/stats",
        description="Агрегация выполняется в PostgreSQL.",
        tests=status_is(200) + [
            "const body = pm.response.json();",
            "pm.test('Есть счётчики по статусам и приоритетам', function () {",
            "    pm.expect(body.total).to.be.a('number');",
            "    pm.expect(Object.keys(body.by_status)).to.include.members(['todo', 'in_progress', 'done']);",
            "    pm.expect(body.overdue).to.be.a('number');",
            "});",
        ],
    ),
    _item(
        "11 · Удалить задачу (DELETE)",
        "DELETE",
        "/api/v1/tasks/{{taskId}}",
        description="Удаление задачи, ответ без тела.",
        tests=status_is(204) + [
            "pm.test('Тело ответа пустое', function () {",
            "    pm.expect(pm.response.text()).to.be.empty;",
            "});",
        ],
    ),
    _item(
        "12 · Проверить, что задача удалена (GET 404)",
        "GET",
        "/api/v1/tasks/{{taskId}}",
        description="После удаления ресурс недоступен.",
        tests=status_is(404) + error_code("TASK_NOT_FOUND"),
    ),
]

error_items = [
    _item(
        "13 · Ошибка валидации: короткое название (422)",
        "POST",
        "/api/v1/tasks",
        description="Минимальная длина названия — 3 символа.",
        body={"title": "ab"},
        tests=status_is(422) + error_code("VALIDATION_ERROR") + [
            "pm.test('Указано проблемное поле', function () {",
            "    pm.expect(pm.response.json().error.details[0].field).to.eql('title');",
            "});",
        ],
    ),
    _item(
        "14 · Ошибка валидации: неизвестное поле (422)",
        "POST",
        "/api/v1/tasks",
        description="Лишние поля запрещены (extra=forbid).",
        body={"title": "Корректное название", "unknown_field": 1},
        tests=status_is(422) + error_code("VALIDATION_ERROR"),
    ),
    _item(
        "15 · Ошибка валидации: недопустимый статус (422)",
        "POST",
        "/api/v1/tasks",
        description="status допускает только todo | in_progress | done.",
        body={"title": "Некорректный статус", "status": "waiting"},
        tests=status_is(422) + error_code("VALIDATION_ERROR"),
    ),
    _item(
        "16 · Ошибка валидации параметра запроса (422)",
        "GET",
        "/api/v1/tasks",
        description="limit должен быть в диапазоне 1..100.",
        query=[("limit", "0")],
        tests=status_is(422) + error_code("VALIDATION_ERROR"),
    ),
    _item(
        "17 · Ошибка валидации пути (422)",
        "GET",
        "/api/v1/tasks/not-a-number",
        description="Идентификатор задачи должен быть целым числом.",
        tests=status_is(422) + error_code("VALIDATION_ERROR"),
    ),
    _item(
        "18 · Битый JSON в теле запроса (400)",
        "POST",
        "/api/v1/tasks",
        description="Синтаксическая ошибка JSON — код 400.",
        body='{"title": "битый json"',
        tests=status_is(400) + error_code("INVALID_JSON"),
    ),
    _item(
        "19 · Несуществующая задача (404)",
        "GET",
        "/api/v1/tasks/999999999",
        description="Задачи с таким id нет.",
        tests=status_is(404) + error_code("TASK_NOT_FOUND"),
    ),
    _item(
        "20 · Удаление несуществующей задачи (404)",
        "DELETE",
        "/api/v1/tasks/999999999",
        description="DELETE тоже возвращает 404, а не 500.",
        tests=status_is(404) + error_code("TASK_NOT_FOUND"),
    ),
    _item(
        "21 · Конфликт: создать задачу для проверки (201)",
        "POST",
        "/api/v1/tasks",
        description="Первая задача с уникальным названием — успех.",
        body={"title": "Конфликт названий {{conflictTitle}}"},
        prerequest=[
            "pm.collectionVariables.set('conflictTitle', 'conf-' + Math.random().toString(36).slice(2, 10));",
        ],
        tests=status_is(201) + [
            "pm.collectionVariables.set('conflictId', pm.response.json().id);",
        ],
    ),
    _item(
        "22 · Конфликт: повторное название (409)",
        "POST",
        "/api/v1/tasks",
        description="UNIQUE-ограничение в БД превращается в понятную ошибку 409.",
        body={"title": "Конфликт названий {{conflictTitle}}"},
        tests=status_is(409) + error_code("CONFLICT"),
    ),
    _item(
        "23 · Уборка: удалить задачу конфликта (204)",
        "DELETE",
        "/api/v1/tasks/{{conflictId}}",
        description="Чистим за собой, чтобы коллекцию можно было прогонять повторно.",
        tests=status_is(204),
    ),
]

collection = {
    "info": {
        "_postman_id": str(uuid.uuid4()),
        "name": "Task Tracker API",
        "description": (
            "Коллекция для проверки микросервиса Task Tracker API (FastAPI + PostgreSQL, docker compose).\n\n"
            "Порядок запуска: `docker compose up -d --build`, затем Run Collection.\n"
            "Переменные: `baseUrl`, `taskId`, `conflictId` — заполняются автоматически."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [
        {"name": "01 · Служебные эндпоинты", "item": service_items, "description": "Health-check и документация"},
        {"name": "02 · Задачи: CRUD", "item": crud_items, "description": "Основные операции с задачами"},
        {"name": "03 · Обработка ошибок", "item": error_items, "description": "Проверка кодов 400/404/409/422"},
    ],
    "variable": [
        {"key": "baseUrl", "value": BASE_URL, "type": "string"},
        {"key": "taskId", "value": "", "type": "string"},
        {"key": "conflictId", "value": "", "type": "string"},
        {"key": "conflictTitle", "value": "", "type": "string"},
    ],
}

environment = {
    "id": str(uuid.uuid4()),
    "name": "Task Tracker Local",
    "values": [
        {"key": "baseUrl", "value": BASE_URL, "type": "default", "enabled": True},
    ],
    "_postman_variable_scope": "environment",
}


def main() -> None:
    POSTMAN_DIR.mkdir(parents=True, exist_ok=True)
    collection_path = POSTMAN_DIR / "task-tracker.postman_collection.json"
    environment_path = POSTMAN_DIR / "task-tracker.postman_environment.json"

    collection_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    environment_path.write_text(json.dumps(environment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total = len(service_items) + len(crud_items) + len(error_items)
    print(f"OK: {collection_path} ({total} запросов)")
    print(f"OK: {environment_path}")


if __name__ == "__main__":
    main()
