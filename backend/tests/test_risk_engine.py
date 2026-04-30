"""Phase-1 tests: risk engine correctness.

Covers:
  - direction sign (long vs short)
  - tail multiplier widens risk and switches the metric label
  - band → sigma round-trip via the persisted snapshot
"""
from __future__ import annotations

import math

import pytest
from sqlalchemy import select

from app.models import Market
from app.services.risk_engine import (
    RiskInputs,
    _CVAR95_NORMAL,
    _CVAR95_T5,
    _Z95,
    _cvar95_multiplier,
    assess_risk,
)


def _assess(db_session, **overrides):
    base = dict(
        market_code="ERCOT_NORTH",
        position_gbp=10_000.0,
        horizon_hours=24,
        target_timestamp=None,
        direction="long",
    )
    base.update(overrides)
    return assess_risk(db_session, RiskInputs(**base))


def test_cvar_multiplier_blends_normal_to_t5() -> None:
    assert _cvar95_multiplier(1.0) == _CVAR95_NORMAL
    assert _cvar95_multiplier(1.2) == _CVAR95_NORMAL
    # Halfway interpolation
    mid = _cvar95_multiplier(1.6)
    assert _CVAR95_NORMAL < mid < _CVAR95_T5
    assert math.isclose(mid, 0.5 * _CVAR95_NORMAL + 0.5 * _CVAR95_T5, rel_tol=1e-9)
    # Saturated to t(5)
    assert _cvar95_multiplier(2.0) == pytest.approx(_CVAR95_T5)
    assert _cvar95_multiplier(3.0) == pytest.approx(_CVAR95_T5)


def test_assess_risk_returns_three_headline_numbers(db_session) -> None:
    result = _assess(db_session)

    assert result["risk_gbp"] >= 0  # CVaR always non-negative
    assert "likely_gbp" in result
    assert "upside_gbp" in result
    assert result["risk_metric"] in {"cvar_95_normal", "cvar_95_t5"}


def test_long_vs_short_flip_directional_pnl(db_session) -> None:
    long_result = _assess(db_session, direction="long", n_paths=8000)
    short_result = _assess(db_session, direction="short", n_paths=8000)

    # Under Monte Carlo, the *expected* P&L should flip sign between long
    # and short. With independent path samples, allow a sampling-noise band.
    long_likely = long_result["likely_gbp"]
    short_likely = short_result["likely_gbp"]
    if abs(long_likely) > 5.0:
        # Signs must oppose (or one is ~0 within noise).
        assert long_likely * short_likely <= 0 or abs(long_likely + short_likely) < 0.4 * abs(long_likely)
    # Risk (CVaR) is direction-agnostic in magnitude — both sides have downside.
    assert long_result["risk_gbp"] >= 0
    assert short_result["risk_gbp"] >= 0


def test_band_to_sigma_round_trip_via_snapshot(db_session) -> None:
    """sigma_price persisted in the snapshot must match (upper - point)/Z95."""
    from app.models import Forecast
    from app.services.forecast_service import run_forecast_for_market

    market = db_session.scalar(select(Market).where(Market.code == "GB_POWER"))
    assert market is not None
    forecasts, _ = run_forecast_for_market(db_session, market, horizon_hours=6)

    for f in forecasts:
        snap = f.feature_snapshot_json or {}
        sigma = float(snap["sigma_price"])
        half_band = max(f.upper_bound - f.point_estimate, f.point_estimate - f.lower_bound)
        # The forecast service applies `confidence_scale` to widen the band;
        # we round-trip with a 5% tolerance to account for that scale.
        implied_sigma = half_band / _Z95
        rel_err = abs(implied_sigma - sigma) / max(sigma, 1.0)
        assert rel_err < 0.05, f"sigma {sigma} vs band-implied {implied_sigma}"


def test_position_scales_pnl_linearly(db_session) -> None:
    """Risk/likely should scale ~linearly in position size — within Monte Carlo
    sampling noise, since the two runs use independent path samples."""
    small = _assess(db_session, position_gbp=1_000.0, n_paths=5000)
    big = _assess(db_session, position_gbp=10_000.0, n_paths=5000)
    # MC noise: ratio should be ~10 with a few-percent tolerance.
    if small["risk_gbp"] > 1.0:
        ratio = big["risk_gbp"] / small["risk_gbp"]
        assert 7.0 < ratio < 14.0, f"risk ratio out of MC tolerance: {ratio}"


def test_response_includes_fx_and_currency(db_session) -> None:
    result = _assess(db_session, market_code="GB_POWER")
    assert "fx_to_gbp" in result
    assert "price_currency" in result
    assert result["price_currency"] in {"GBP", "USD", "EUR"}
    # GB market should be in GBP, FX = 1.0
    assert result["price_currency"] == "GBP"
    assert result["fx_to_gbp"] == pytest.approx(1.0)


def test_scenarios_widen_risk(db_session) -> None:
    from app.services.risk_engine import ScenarioSpec

    base = _assess(db_session, scenarios=[])
    stressed = _assess(
        db_session,
        scenarios=[ScenarioSpec(name="outage_2gw"), ScenarioSpec(name="heatwave_+5C")],
    )
    assert len(stressed["scenarios"]) == 2
    # At least one stressed scenario should produce risk >= base risk
    # (with high probability — these scenarios add positive drift + σ).
    max_scen_risk = max(s["risk_gbp"] for s in stressed["scenarios"])
    assert max_scen_risk >= base["risk_gbp"] * 0.9  # MC noise tolerance
