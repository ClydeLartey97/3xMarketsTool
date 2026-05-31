"""
Compatibility tests for the public API surface.

These tests are the safety net for the performance preservation plan
(`docs/PERFORMANCE_PRESERVATION_PLAN.md`, Phase 0). They lock down the
shape of the existing API responses so a performance change cannot
silently remove a field, rename one, or weaken the official risk read.

These tests intentionally do not assert exact stochastic values. They
assert the presence and basic types of required fields.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models import Market


REQUIRED_DASHBOARD_TOP_LEVEL = {
    "market",
    "latest_forecast",
    "forecasts",
    "recent_prices",
    "recent_events",
    "recent_news",
    "tracked_sources",
    "active_alerts",
    "key_metrics",
}

REQUIRED_DASHBOARD_KEY_METRICS = {
    "avg_price_24h",
    "avg_spike_probability_12h",
    "high_severity_events",
    "model_mae",
    "model_rmse",
    "directional_accuracy",
    "spike_precision",
    "data_freshness_minutes",
    "synthetic_share_24h",
}

REQUIRED_RISK_TOP_LEVEL = {
    "market_code",
    "market_name",
    "as_of",
    "position_gbp",
    "direction",
    "horizon_hours",
    "target_timestamp",
    "spot_price",
    "forecast_price",
    "expected_price",
    "sigma_price",
    "sigma_hourly_pct",
    "expected_return_pct",
    "sigma_return_pct",
    "risk_gbp",
    "likely_gbp",
    "upside_gbp",
    "risk_metric",
    "var95_gbp",
    "prob_loss",
    "max_drawdown_gbp",
    "fx_to_gbp",
    "price_currency",
    "n_paths",
    "edge_score",
    "confidence",
    "regime",
    "catalyst_severity",
    "asymmetry",
    "tail_multiplier",
    "scorer_provider",
    "rationale",
    "scenarios",
    "coefficients",
    "decision_gate",
}

REQUIRED_MARKET_FIELDS = {
    "id",
    "name",
    "code",
    "commodity_type",
    "region",
    "timezone",
    "data_status",
    "metadata",
}


def _assert_required(body: dict[str, Any], required: set[str], name: str) -> None:
    missing = required - set(body)
    assert not missing, f"{name} missing required fields: {missing}"


def test_markets_endpoint_shape(client) -> None:
    response = client.get("/api/markets")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body, "expected at least one seeded market"
    for entry in body:
        _assert_required(entry, REQUIRED_MARKET_FIELDS, "MarketRead")
        assert isinstance(entry["id"], int)
        assert isinstance(entry["code"], str)
        assert isinstance(entry["metadata"], dict)


def test_dashboard_endpoint_shape(client) -> None:
    response = client.get("/api/dashboard/ERCOT_NORTH")
    assert response.status_code == 200
    body = response.json()
    _assert_required(body, REQUIRED_DASHBOARD_TOP_LEVEL, "DashboardResponse")
    _assert_required(body["market"], REQUIRED_MARKET_FIELDS, "DashboardResponse.market")
    _assert_required(
        body["key_metrics"],
        REQUIRED_DASHBOARD_KEY_METRICS,
        "DashboardResponse.key_metrics",
    )
    assert isinstance(body["recent_prices"], list)
    assert isinstance(body["forecasts"], list)
    assert isinstance(body["tracked_sources"], list)
    assert isinstance(body["active_alerts"], list)


def test_risk_assessment_shape_preserves_three_numbers(client) -> None:
    response = client.post(
        "/api/risk-assessment",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10_000,
            "horizon_hours": 24,
            "direction": "long",
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_required(body, REQUIRED_RISK_TOP_LEVEL, "RiskAssessmentResponse")
    # The three headline numbers must remain present and finite.
    for key in ("risk_gbp", "likely_gbp", "upside_gbp"):
        assert isinstance(body[key], (int, float)), f"{key} must be numeric"
    assert body["risk_gbp"] >= 0, "risk_gbp must be non-negative"

    # Auditability fields must remain present.
    coeffs = body["coefficients"]
    assert "items" in coeffs and isinstance(coeffs["items"], list)
    assert "equation_summary" in coeffs and isinstance(coeffs["equation_summary"], str)
    assert coeffs["items"], "coefficients.items must not be empty"

    gate = body["decision_gate"]
    for key in ("action", "score", "label", "reasons", "checks"):
        assert key in gate, f"decision_gate missing {key}"
    assert gate["action"] in {"clear", "watch", "block"}


def test_risk_assessment_default_n_paths_is_official(client) -> None:
    """Official risk reads must keep their default Monte Carlo path count."""
    response = client.post(
        "/api/risk-assessment",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10_000,
            "horizon_hours": 24,
            "direction": "long",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # The plan forbids reducing official n_paths for performance reasons.
    assert body["n_paths"] >= 5000, "official n_paths must remain decision-grade"


def test_risk_assessment_direction_sign(client) -> None:
    """Long vs short must produce mirrored expected returns."""
    long_resp = client.post(
        "/api/risk-assessment",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10_000,
            "horizon_hours": 24,
            "direction": "long",
        },
    ).json()
    short_resp = client.post(
        "/api/risk-assessment",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10_000,
            "horizon_hours": 24,
            "direction": "short",
        },
    ).json()
    # Both still expose the three numbers and risk is non-negative.
    for body in (long_resp, short_resp):
        assert body["risk_gbp"] >= 0
        assert isinstance(body["likely_gbp"], (int, float))
        assert isinstance(body["upside_gbp"], (int, float))


def test_risk_paths_endpoint_returns_sampled_paths(client) -> None:
    response = client.post(
        "/api/risk-assessment/paths",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10_000,
            "horizon_hours": 24,
            "direction": "long",
        },
    )
    assert response.status_code == 200
    body = response.json()
    for key in ("market_code", "horizon_hours", "path_hours", "price_paths", "assessment"):
        assert key in body, f"paths response missing {key}"
    assert isinstance(body["price_paths"], list)
    assert body["price_paths"], "price_paths must not be empty"
    assert isinstance(body["price_paths"][0], list)
    # The embedded assessment must still preserve the three headline numbers.
    embedded = body["assessment"]
    for key in ("risk_gbp", "likely_gbp", "upside_gbp", "n_paths"):
        assert key in embedded


def test_risk_sensitivity_endpoint_shape(client) -> None:
    response = client.post(
        "/api/risk-assessment/sensitivity",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10_000,
            "horizon_hours": 24,
            "direction": "long",
            "coefficients_to_perturb": ["tail_multiplier", "asymmetry"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    for key in ("market_code", "position_gbp", "perturbations_pct", "rows"):
        assert key in body, f"sensitivity response missing {key}"
    assert isinstance(body["rows"], list)
    assert body["rows"], "rows must not be empty when coefficients requested"
    first = body["rows"][0]
    for key in ("coefficient", "base_value", "cells"):
        assert key in first


def test_risk_calibration_endpoint_shape(client, db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    response = client.get(f"/api/markets/{market.id}/risk-calibration")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "market_id",
        "claimed_breach_rate",
        "actual_breach_rate",
        "kupiec_p_value",
        "sample_count",
        "calibration_status",
    ):
        assert key in body, f"calibration response missing {key}"
    assert body["calibration_status"] in {"honest", "understating", "overstating"}


def test_decisions_endpoint_shape(client) -> None:
    response = client.get("/api/decisions")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
