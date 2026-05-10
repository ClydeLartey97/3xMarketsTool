from sqlalchemy import select

from app.models import RiskAssessmentLog


def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_endpoint(client) -> None:
    response = client.get("/api/dashboard/ERCOT_NORTH")
    assert response.status_code == 200
    body = response.json()
    assert body["market"]["code"] == "ERCOT_NORTH"
    assert len(body["recent_prices"]) > 0
    assert len(body["recent_news"]) > 0
    assert len(body["tracked_sources"]) >= 20
    assert "avg_price_24h" in body["key_metrics"]


def test_ingest_article(client) -> None:
    response = client.post(
        "/api/articles/ingest",
        json={
            "title": "Transmission outage creates local constraint in Houston",
            "body": "A transmission outage is expected to constrain imports and lift local power prices.",
            "source_name": "Ops Note",
            "source_url": "https://example.com/outage",
            "published_at": "2026-03-16T10:00:00Z",
            "market_code": "ERCOT_HOUSTON",
        },
    )
    assert response.status_code == 200
    assert response.json()["event_type"] == "transmission_outage"


def test_risk_assessment_endpoint(client, db_session) -> None:
    response = client.post(
        "/api/risk-assessment",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10000,
            "horizon_hours": 24,
            "direction": "long",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["market_code"] == "ERCOT_NORTH"
    assert body["risk_gbp"] >= 0
    assert body["scorer_provider"] in {"heuristic", "gemini"}
    logged = db_session.scalar(select(RiskAssessmentLog).order_by(RiskAssessmentLog.id.desc()))
    assert logged is not None
    assert logged.market_id is not None
    assert logged.risk_gbp == body["risk_gbp"]


def test_risk_assessment_solve_endpoint(client) -> None:
    response = client.post(
        "/api/risk-assessment/solve",
        json={
            "market_code": "ERCOT_NORTH",
            "max_risk_gbp": 500,
            "horizon_hours": 24,
            "direction": "long",
            "position_unit": "GBP",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["converged"] is True
    assert body["risk_error_pct"] <= body["tolerance_pct"]
    assert body["resolved_request"]["position_gbp"] > 0
    assert body["assessment"]["risk_gbp"] >= 490
    assert body["assessment"]["risk_gbp"] <= 510


def test_risk_assessment_sensitivity_endpoint(client) -> None:
    response = client.post(
        "/api/risk-assessment/sensitivity",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10000,
            "horizon_hours": 24,
            "direction": "long",
            "n_paths": 500,
            "coefficients_to_perturb": ["tail_multiplier"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rows"][0]["coefficient"] == "tail_multiplier"
    risks = [cell["risk_gbp"] for cell in body["rows"][0]["cells"]]
    assert risks == sorted(risks)


def test_risk_assessment_paths_endpoint_caps_payload(client) -> None:
    response = client.post(
        "/api/risk-assessment/paths",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10000,
            "horizon_hours": 12,
            "direction": "long",
            "n_paths": 500,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["price_paths"]) == 200
    assert len(body["price_paths"][0]) == 13
    assert body["assessment"]["market_code"] == "ERCOT_NORTH"


def test_market_timeseries_endpoint_returns_aligned_fundamentals(client, db_session) -> None:
    from app.models import Market

    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    response = client.get(f"/api/markets/{market.id}/timeseries?series=demand,wind,solar&limit=24")

    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert {"timestamp", "demand_mw", "wind_mw", "solar_mw", "wind_share", "solar_share"} <= set(body[0])
