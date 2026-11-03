def test_register_user(client):
    response = client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "investor@example.com",
            "password": "SecurePassword123!"
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["username"] == "TestInvestor"
    assert data["email"] == "investor@example.com"
    assert "password_hash" not in data


def test_duplicate_username(client):
    client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "first@example.com",
            "password": "SecurePassword123!",
        },
    )

    response = client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "second@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 409


def test_duplicate_email(client):
    client.post(
        "/register",
        json={
            "username": "InvestorOne",
            "email": "same@example.com",
            "password": "SecurePassword123!",
        },
    )

    response = client.post(
        "/register",
        json={
            "username": "InvestorTwo",
            "email": "same@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 409


def test_invalid_email(client):
    response = client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "not-an-email",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 422


def test_short_password(client):
    response = client.post(
        "/register",
        json={
            "username": "TestInvestor",
            "email": "test@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422
