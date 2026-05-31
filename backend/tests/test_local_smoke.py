"""Fast local smoke tests for the default developer loop."""

from __future__ import annotations


def test_health_endpoint_is_public(anon_client) -> None:
    response = anon_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_authenticated_markets_endpoint_runs(client) -> None:
    response = client.get("/api/markets")
    assert response.status_code == 200
    markets = response.json()
    assert isinstance(markets, list)
    assert markets
    assert {"id", "code", "name"} <= set(markets[0])


def test_markets_overview_endpoint_runs(client) -> None:
    response = client.get("/api/markets/overview")
    assert response.status_code == 200
    overview = response.json()
    assert isinstance(overview, list)
    assert overview
    assert {"market", "spot", "next_forecast", "data_status"} <= set(overview[0])
