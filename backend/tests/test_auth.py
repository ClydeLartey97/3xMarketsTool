from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth import create_access_token, hash_password
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _make_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("secret-password"),
        organisation="3x Test",
        role="analyst",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_anonymous_market_request_is_rejected(anon_client: TestClient) -> None:
    response = anon_client.get("/api/markets")
    assert response.status_code == 401


def test_authenticated_market_request_succeeds(client: TestClient) -> None:
    response = client.get("/api/markets")
    assert response.status_code == 200
    assert response.json()


def test_login_returns_bearer_token(anon_client: TestClient, auth_user: User) -> None:
    response = anon_client.post(
        "/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2
    assert body["user"]["email"] == TEST_USER_EMAIL


def test_registration_is_disabled_by_default(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/api/auth/register",
        json={
            "email": "new-user@3x.local",
            "password": "strong-password",
            "organisation": "3x Test",
            "role": "admin",
        },
    )
    assert response.status_code == 403


def test_user_cannot_read_or_mutate_another_users_decisions(
    anon_client: TestClient,
    db_session: Session,
) -> None:
    user_a = _make_user(db_session, "owner-a@3x.local")
    user_b = _make_user(db_session, "owner-b@3x.local")
    headers_a = {"Authorization": f"Bearer {create_access_token(user_a)}"}
    headers_b = {"Authorization": f"Bearer {create_access_token(user_b)}"}

    payload = {
        "market_code": "ERCOT_NORTH",
        "position_gbp": 10_000,
        "direction": "long",
        "horizon_hours": 24,
        "risk_gbp": 500,
        "likely_gbp": 120,
        "upside_gbp": 800,
        "thesis_text": "basis tightening into peak",
    }
    decision_a = anon_client.post("/api/decisions", json=payload, headers=headers_a).json()
    decision_b = anon_client.post(
        "/api/decisions",
        json={**payload, "thesis_text": "separate user thesis"},
        headers=headers_b,
    ).json()

    response = anon_client.get("/api/decisions", headers=headers_a)
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert decision_a["id"] in ids
    assert decision_b["id"] not in ids

    patch_response = anon_client.patch(
        f"/api/decisions/{decision_b['id']}",
        json={"thesis_text": "not mine"},
        headers=headers_a,
    )
    assert patch_response.status_code == 404

    delete_response = anon_client.delete(f"/api/decisions/{decision_b['id']}", headers=headers_a)
    assert delete_response.status_code == 404
