from decimal import Decimal

from sqlalchemy import select

from larp_finance.models import Portfolio, User


def test_registration_creates_portfolio(client, db_session):
    response = client.post(
        "/register",
        json={
            "username": "PortfolioTester",
            "email": "portfolio@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 201

    user_id = response.json()["id"]

    portfolio = db_session.scalar(
        select(Portfolio).where(Portfolio.user_id == user_id)
    )

    assert portfolio is not None
    assert portfolio.cash_balance == Decimal("10000.00")


def test_get_own_portfolio(client):
    registration = client.post(
        "/register",
        json={
            "username": "InvestorOne",
            "email": "investor@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert registration.status_code == 201

    login = client.post(
        "/login",
        json={
            "username": "InvestorOne",
            "password": "SecurePassword123!",
        },
    )

    assert login.status_code == 200

    token = login.json()["access_token"]

    response = client.get(
        "/portfolio/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == registration.json()["id"]
    assert Decimal(response.json()["cash_balance"]) == Decimal("10000.00")


def test_portfolio_requires_authentication(client):
    response = client.get("/portfolio/me")

    assert response.status_code == 401
