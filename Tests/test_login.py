import pytest


@pytest.fixture
def registered_user(client):
    response = client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "investor@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 201

    return {
        "username": "TestInvestor",
        "password": "SecurePassword123!",
    }


def test_login_success(client, registered_user):
    response = client.post(
        "/login",
        json=registered_user,
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, registered_user):
    response = client.post(
        "/login",
        json={
            "username": registered_user["username"],
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_login_unknown_user(client):
    response = client.post(
        "/login",
        json={
            "username": "NonexistentUser",
            "password": "SomePassword123!",
        },
    )

    assert response.status_code == 401
