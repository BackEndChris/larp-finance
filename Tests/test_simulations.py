from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from larp_finance.models import Asset, Simulation, User


def register_and_login(client, username, email):
    password = "TestPassword123!"

    register_response = client.post(
        "/register",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


def create_test_asset(db_session):
    asset = Asset(
        symbol="SIMTEST",
        name="Simulation Test Asset",
        asset_type="stock",
    )

    db_session.add(asset)
    db_session.flush()

    return asset


def valid_payload(asset_id):
    return {
        "asset_id": asset_id,
        "initial_investment": "1000.00",
        "purchase_date": "2023-01-01",
    }


# Test 1: Authentication is required

def test_simulation_requires_authentication(client):
    response = client.post(
        "/simulations",
        json={
            "asset_id": 1,
            "initial_investment": "1000.00",
            "purchase_date": "2023-01-01",
        },
    )

    assert response.status_code == 401


# Test 2: Successful creation and database persistence

def test_create_simulation_success(client, db_session):
    headers = register_and_login(
        client,
        "SimulationTester",
        "simulationtester@example.com",
    )
    asset = create_test_asset(db_session)

    response = client.post(
        "/simulations",
        json=valid_payload(asset.id),
        headers=headers,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["asset_id"] == asset.id
    assert Decimal(data["initial_investment"]) == Decimal("1000.00")
    assert data["status"] == "pending"

    simulation = db_session.get(Simulation, data["id"])

    assert simulation is not None
    assert simulation.user_id == data["user_id"]
    assert simulation.status == "pending"
    assert simulation.final_value is None
    assert simulation.profit_loss is None


# Test 3: Today's and future dates are rejected

def test_simulation_rejects_nonhistorical_dates(client, db_session):
    headers = register_and_login(
        client,
        "DateTester",
        "datetester@example.com",
    )
    asset = create_test_asset(db_session)

    for invalid_date in [
        date.today(),
        date.today() + timedelta(days=1),
    ]:
        payload = valid_payload(asset.id)
        payload["purchase_date"] = invalid_date.isoformat()

        response = client.post(
            "/simulations",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422


# Test 4: Invalid investment amounts are rejected

def test_simulation_rejects_invalid_investment(client, db_session):
    headers = register_and_login(
        client,
        "AmountTester",
        "amounttester@example.com",
    )
    asset = create_test_asset(db_session)

    for invalid_amount in ["0.00", "-10.00", "1.123"]:
        payload = valid_payload(asset.id)
        payload["initial_investment"] = invalid_amount

        response = client.post(
            "/simulations",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422


# Test 5: Unknown assets are rejected

def test_simulation_rejects_unknown_asset(client):
    headers = register_and_login(
        client,
        "AssetTester",
        "assettester@example.com",
    )

    response = client.post(
        "/simulations",
        json=valid_payload(999999),
        headers=headers,
    )

    assert response.status_code == 404


# Test 6: Each simulation belongs to its creator

def test_simulation_ownership(client, db_session):
    headers_a = register_and_login(
        client,
        "OwnerA",
        "ownera@example.com",
    )
    headers_b = register_and_login(
        client,
        "OwnerB",
        "ownerb@example.com",
    )

    asset = create_test_asset(db_session)

    response_a = client.post(
        "/simulations",
        json=valid_payload(asset.id),
        headers=headers_a,
    )

    response_b = client.post(
        "/simulations",
        json=valid_payload(asset.id),
        headers=headers_b,
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201

    simulation_a = db_session.get(
        Simulation,
        response_a.json()["id"],
    )
    simulation_b = db_session.get(
        Simulation,
        response_b.json()["id"],
    )

    assert simulation_a.user_id != simulation_b.user_id
    assert simulation_a.user_id == response_a.json()["user_id"]
    assert simulation_b.user_id == response_b.json()["user_id"]


# Test 7: Owner can retrieve their simulation

def test_get_own_simulation(client, db_session):
    headers = register_and_login(
        client,
        "RetrieveOwner",
        "retrieveowner@example.com",
    )
    asset = create_test_asset(db_session)

    created = client.post(
        "/simulations",
        json=valid_payload(asset.id),
        headers=headers,
    )

    assert created.status_code == 201

    simulation_id = created.json()["id"]

    response = client.get(
        f"/simulations/{simulation_id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == simulation_id
    assert response.json()["status"] == "pending"
    assert response.json()["final_value"] is None


# Test 8: Another user cannot retrieve the simulation

def test_cannot_retrieve_another_users_simulation(
    client,
    db_session,
):
    headers_a = register_and_login(
        client,
        "PrivateOwner",
        "privateowner@example.com",
    )
    headers_b = register_and_login(
        client,
        "OtherUser",
        "otheruser@example.com",
    )

    asset = create_test_asset(db_session)

    created = client.post(
        "/simulations",
        json=valid_payload(asset.id),
        headers=headers_a,
    )

    assert created.status_code == 201

    simulation_id = created.json()["id"]

    response = client.get(
        f"/simulations/{simulation_id}",
        headers=headers_b,
    )

    assert response.status_code == 404


# Test 9: Unknown simulation returns 404

def test_get_unknown_simulation(client):
    headers = register_and_login(
        client,
        "UnknownSimulationUser",
        "unknownsimulation@example.com",
    )

    response = client.get(
        "/simulations/999999",
        headers=headers,
    )

    assert response.status_code == 404
