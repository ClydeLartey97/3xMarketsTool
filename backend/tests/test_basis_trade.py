"""Phase-E.3 tests: cross-zone basis trade type."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Market
from app.services.risk_engine import RiskInputs, assess_risk


def _assess(db_session, **kwargs):
    base = dict(
        market_code="GB_POWER",
        position_gbp=10_000.0,
        horizon_hours=24,
        target_timestamp=None,
        direction="long",
        random_seed=12345,
        n_paths=2000,
    )
    base.update(kwargs)
    return assess_risk(db_session, RiskInputs(**base))


def test_basis_meta_populated_when_paired_market_set(db_session) -> None:
    result = _assess(db_session, basis_against_market_code="EPEX_DE", basis_direction="long")
    basis = result["basis"]
    assert basis is not None
    assert basis["primary_market_code"] == "GB_POWER"
    assert basis["basis_market_code"] == "EPEX_DE"
    assert basis["basis_direction"] == "long"
    assert "correlation_rho" in basis
    assert -1.0 <= basis["correlation_rho"] <= 1.0
    assert basis["primary_spot"] > 0
    assert basis["basis_spot"] > 0


def test_basis_meta_is_none_for_outright_trade(db_session) -> None:
    result = _assess(db_session)
    assert result["basis"] is None


def test_basis_long_vs_short_have_opposite_expected_pnl(db_session) -> None:
    long_spread = _assess(db_session, basis_against_market_code="EPEX_DE",
                          basis_direction="long", n_paths=4000)
    short_spread = _assess(db_session, basis_against_market_code="EPEX_DE",
                           basis_direction="short", n_paths=4000)
    # Expected P&L on the long spread should be the negative of expected
    # P&L on the short spread (within Monte Carlo sampling tolerance).
    a = long_spread["likely_gbp"]
    b = short_spread["likely_gbp"]
    if abs(a) > 5.0:
        assert (a > 0) != (b > 0) or abs(a + b) < 0.5 * abs(a)
    # Both legs have downside, so CVaR is non-negative in both directions
    assert long_spread["risk_gbp"] >= 0
    assert short_spread["risk_gbp"] >= 0


def test_basis_unknown_market_raises(db_session) -> None:
    with pytest.raises(ValueError):
        _assess(db_session, basis_against_market_code="NOT_A_MARKET")


def test_basis_against_same_market_falls_through_to_outright(db_session) -> None:
    """If basis_against equals primary, the engine should treat it as outright."""
    result = _assess(db_session, basis_against_market_code="GB_POWER")
    assert result["basis"] is None
