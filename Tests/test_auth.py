from datetime import datetime, timedelta, timezone

import jwt

from larp_finance.models import User
from larp_finance.security import (
    ALGORITHM,
    JWT_SECRET_KEY,
    create_access_token,
)


def test_valid_token(client):
    registration = client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "investor@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert registration.status_code == 201

    login = client.post(
        "/login",
        json={
            "username": "TestInvestor",
            "password": "SecurePassword123!",
        },
    )

    assert login.status_code == 200

    token = login.json()["access_token"]

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "TestInvestor"
    assert response.json()["email"] == "investor@example.com"
    assert "password_hash" not in response.json()


def test_missing_token(client):
    response = client.get("/users/me")

    assert response.status_code == 401


def test_invalid_token(client):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalidtoken123"},
    )

    assert response.status_code == 401


def test_expired_token(client):
    expired_token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        JWT_SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401


def test_nonexistent_user_token(client, db_session):
    nonexistent_id = 2147483647

    assert db_session.get(User, nonexistent_id) is None

    token = create_access_token(nonexistent_id)

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_blank_signing_secret_rejects_startup():
    import os
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-c", "import larp_finance.security"],
        env={**os.environ, "JWT_SECRET_KEY": " "},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert "JWT_SECRET_KEY must not be blank" in result.stderr
