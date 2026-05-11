from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth import create_access_token, hash_password


def _sensitivity_payload() -> dict:
    return {
        "market_code": "ERCOT_NORTH",
        "position_gbp": 10000,
        "horizon_hours": 24,
        "direction": "long",
        "n_paths": 500,
        "coefficients_to_perturb": ["tail_multiplier"],
    }


def _fake_sensitivity(*args, **kwargs) -> dict:
    return {
        "market_code": "ERCOT_NORTH",
        "position_gbp": 10000,
        "direction": "long",
        "horizon_hours": 24,
        "perturbations_pct": [-0.5, -0.25, 0, 0.25, 0.5],
        "rows": [
            {
                "coefficient": "tail_multiplier",
                "base_value": 1.0,
                "cells": [
                    {"perturbation_pct": -0.5, "risk_gbp": 1, "likely_gbp": 0, "upside_gbp": 1},
                    {"perturbation_pct": -0.25, "risk_gbp": 2, "likely_gbp": 0, "upside_gbp": 1},
                    {"perturbation_pct": 0, "risk_gbp": 3, "likely_gbp": 0, "upside_gbp": 1},
                    {"perturbation_pct": 0.25, "risk_gbp": 4, "likely_gbp": 0, "upside_gbp": 1},
                    {"perturbation_pct": 0.5, "risk_gbp": 5, "likely_gbp": 0, "upside_gbp": 1},
                ],
            }
        ],
    }


def test_rate_limits_are_per_user_and_route_specific(
    anon_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    for _ in range(60):
        assert anon_client.get("/api/markets", headers=auth_headers).status_code == 200
    assert anon_client.get("/api/markets", headers=auth_headers).status_code == 429

    other_user = User(
        email="rate-limit-other@3x.local",
        password_hash=hash_password("rate-limit-password"),
        organisation="3x Test",
        role="analyst",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)
    other_headers = {"Authorization": f"Bearer {create_access_token(other_user)}"}
    assert anon_client.get("/api/markets", headers=other_headers).status_code == 200

    from app.api import routes

    monkeypatch.setattr(routes, "run_risk_sensitivity", _fake_sensitivity)
    for _ in range(5):
        response = anon_client.post(
            "/api/risk-assessment/sensitivity",
            json=_sensitivity_payload(),
            headers=other_headers,
        )
        assert response.status_code == 200
    response = anon_client.post(
        "/api/risk-assessment/sensitivity",
        json=_sensitivity_payload(),
        headers=other_headers,
    )
    assert response.status_code == 429
