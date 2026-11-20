"""Интеграционные тесты API (pytest + FastAPI TestClient).

Запуск требует доступной БД PostgreSQL со схемой из ``db/init``:

    DATABASE_URL=postgresql+psycopg://task_user:task_pass@localhost:5433/taskdb pytest -q
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def task_payload() -> dict:
    """Уникальное название, чтобы тесты не конфликтовали между запусками."""
    return {
        "title": f"pytest-задача-{uuid.uuid4().hex[:8]}",
        "description": "Создано автотестом",
        "status": "todo",
        "priority": "medium",
    }


@pytest.fixture()
def created_task(client: TestClient, task_payload: dict) -> dict:
    response = client.post("/api/v1/tasks", json=task_payload)
    assert response.status_code == 201, response.text
    task = response.json()
    yield task
    client.delete(f"/api/v1/tasks/{task['id']}")


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "taskdb"
    assert "PostgreSQL" in body["server_version"]


def test_create_and_get(client: TestClient, task_payload: dict) -> None:
    created = client.post("/api/v1/tasks", json=task_payload)
    assert created.status_code == 201
    assert created.headers["Location"].startswith("/api/v1/tasks/")

    task_id = created.json()["id"]
    fetched = client.get(f"/api/v1/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == task_payload["title"]

    client.delete(f"/api/v1/tasks/{task_id}")


def test_duplicate_title_returns_409(client: TestClient, created_task: dict) -> None:
    response = client.post("/api/v1/tasks", json={"title": created_task["title"]})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"


def test_patch_updates_only_given_fields(client: TestClient, created_task: dict) -> None:
    response = client.patch(
        f"/api/v1/tasks/{created_task['id']}",
        json={"status": "done", "priority": "high"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["priority"] == "high"
    assert body["title"] == created_task["title"]
    assert body["updated_at"] >= created_task["updated_at"]


def test_delete_removes_task(client: TestClient, task_payload: dict) -> None:
    created = client.post("/api/v1/tasks", json=task_payload).json()
    deleted = client.delete(f"/api/v1/tasks/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/tasks/{created['id']}").status_code == 404


def test_validation_error(client: TestClient) -> None:
    response = client.post("/api/v1/tasks", json={"title": "ab"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == "title"


def test_unknown_field_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/tasks", json={"title": "корректное название", "unknown": 1})
    assert response.status_code == 422


def test_invalid_json_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks",
        content=b'{"title": "broken json"',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"


def test_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/999999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_list_filters_and_pagination(client: TestClient, created_task: dict) -> None:
    response = client.get("/api/v1/tasks", params={"status": "todo", "limit": 5, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 5
    assert all(item["status"] == "todo" for item in body["items"])


def test_stats(client: TestClient, created_task: dict) -> None:
    response = client.get("/api/v1/tasks/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert set(body["by_status"]) == {"todo", "in_progress", "done"}


def test_openapi_schema_available(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/tasks" in response.json()["paths"]
