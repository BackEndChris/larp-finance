from types import SimpleNamespace
from uuid import uuid4

import larp_finance.routers.tasks as tasks_router

from kombu.exceptions import OperationalError


def authenticated_headers(client):
    client.post(
        "/register",
        json={
            "username": "CeleryTester",
            "email": "celerytester@example.com",
            "password": "TestPassword123!",
        },
    )

    response = client.post(
        "/login",
        json={
            "username": "CeleryTester",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200

    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


# Test 1: Submission requires authentication

def test_task_submission_requires_authentication(client):
    response = client.post(
        "/tasks/add",
        json={"a": 2, "b": 3},
    )

    assert response.status_code == 401


# Test 2: Successful task submission

def test_submit_addition(client, monkeypatch):
    headers = authenticated_headers(client)
    task_id = str(uuid4())

    def mock_delay(a, b):
        assert a == 2
        assert b == 3

        return SimpleNamespace(id=task_id)

    monkeypatch.setattr(
        tasks_router.add_numbers,
        "delay",
        mock_delay,
    )

    response = client.post(
        "/tasks/add",
        json={"a": 2, "b": 3},
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json() == {
        "task_id": task_id,
        "status": "submitted",
    }


# Test 3: Task queue unavailable

def test_task_submission_queue_unavailable(client, monkeypatch):
    headers = authenticated_headers(client)

    def mock_delay(a, b):
        raise OperationalError("Redis unavailable")

    monkeypatch.setattr(
        tasks_router.add_numbers,
        "delay",
        mock_delay,
    )

    response = client.post(
        "/tasks/add",
        json={"a": 2, "b": 3},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Task queue temporarily unavailable"
    )


# Test 4: Successful task result retrieval

def test_get_completed_task(client, monkeypatch):
    headers = authenticated_headers(client)
    task_id = str(uuid4())

    class MockResult:
        state = "SUCCESS"
        result = 5

        def successful(self):
            return True

    def mock_async_result(received_id):
        assert received_id == task_id
        return MockResult()

    monkeypatch.setattr(
        tasks_router.celery_app,
        "AsyncResult",
        mock_async_result,
    )

    response = client.get(
        f"/tasks/{task_id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_id": task_id,
        "status": "SUCCESS",
        "result": 5,
    }


# Test 5: Invalid task ID

def test_invalid_task_id(client):
    headers = authenticated_headers(client)

    response = client.get(
        "/tasks/not-a-valid-uuid",
        headers=headers,
    )

    assert response.status_code == 422


def test_unavailable_task_backend_returns_503(client, monkeypatch):
    from redis.exceptions import ConnectionError
    headers = authenticated_headers(client)
    class UnavailableResult:
        @property
        def state(self):
            raise ConnectionError("private connection details")
    monkeypatch.setattr(tasks_router.celery_app, "AsyncResult", lambda task_id: UnavailableResult())
    response = client.get(f"/tasks/{uuid4()}", headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "Task results temporarily unavailable"}
