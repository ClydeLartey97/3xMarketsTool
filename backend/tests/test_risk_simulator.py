"""Phase-2 tests: Monte Carlo simulator + FX path."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from app.services.risk_simulator import (
    SimConfig,
    empirical_max_drawdown,
    empirical_risk_metrics,
    pnl_from_paths,
    simulate_price_paths,
)


def test_zero_vol_zero_drift_produces_flat_paths() -> None:
    cfg = SimConfig(n_paths=100, horizon_hours=24, spot=50.0, sigma_hourly=0.0, drift_hourly=0.0, seed=1)
    result = simulate_price_paths(cfg)
    assert result.paths.shape == (100, 25)
    assert np.allclose(result.paths, 50.0)


def test_terminal_distribution_matches_analytic_gaussian() -> None:
    """With Gaussian shocks, terminal log-return has mean ≈ h*drift and σ ≈ √h * σ_h."""
    h = 24
    sigma_h = 0.04
    drift_h = 0.001
    cfg = SimConfig(n_paths=20_000, horizon_hours=h, spot=100.0,
                    sigma_hourly=sigma_h, drift_hourly=drift_h, seed=42)
    result = simulate_price_paths(cfg)
    log_terminal = np.log(result.terminal_prices / 100.0)

    expected_mean = h * drift_h
    expected_sigma = np.sqrt(h) * sigma_h

    assert abs(log_terminal.mean() - expected_mean) < 0.005
    assert abs(log_terminal.std(ddof=0) - expected_sigma) < 0.01


def test_tail_multiplier_increases_kurtosis() -> None:
    h = 12
    cfg_normal = SimConfig(n_paths=15_000, horizon_hours=h, spot=100.0,
                           sigma_hourly=0.05, tail_multiplier=1.0, seed=7)
    cfg_heavy = SimConfig(n_paths=15_000, horizon_hours=h, spot=100.0,
                          sigma_hourly=0.05, tail_multiplier=2.0, seed=7)
    norm_term = np.log(simulate_price_paths(cfg_normal).terminal_prices / 100.0)
    heavy_term = np.log(simulate_price_paths(cfg_heavy).terminal_prices / 100.0)
    assert stats.kurtosis(heavy_term, fisher=False) > stats.kurtosis(norm_term, fisher=False)


def test_pnl_mwh_position_is_path_independent_of_spot() -> None:
    """For a 100 MWh long position, P&L = 100 × (P_T − P_0) regardless of spot scale."""
    cfg = SimConfig(n_paths=2000, horizon_hours=6, spot=80.0,
                    sigma_hourly=0.03, drift_hourly=0.0, seed=11)
    result = simulate_price_paths(cfg)
    pnl = pnl_from_paths(result, direction_sign=1.0, position_native=100.0, position_unit="MWh")
    expected = 100.0 * (result.terminal_prices - result.paths[:, 0])
    assert np.allclose(pnl, expected)


def test_empirical_metrics_are_consistent() -> None:
    pnl = np.array([-500, -200, -100, -50, 0, 50, 100, 200, 300, 1000], dtype=float)
    m = empirical_risk_metrics(pnl)
    assert m["likely_gbp"] == pytest.approx(pnl.mean())
    assert m["upside_gbp"] == pytest.approx(np.percentile(pnl, 95))
    assert m["var95_gbp"] >= 0
    assert m["cvar95_gbp"] >= m["var95_gbp"]  # CVaR ≥ VaR by definition
    assert 0.0 <= m["prob_loss"] <= 1.0
    assert m["prob_loss"] == pytest.approx((pnl < 0).mean())


def test_fx_conversion_path() -> None:
    """USD market with position_gbp=10000 long, FX 0.8 USD→GBP.

    The risk engine first converts £10,000 → $12,500 native notional, then
    the simulator produces a P&L in USD, which is converted back to GBP at 0.8.
    Round-trip should preserve the GBP scale: a 1% move yields ~£100.
    """
    fx = 0.8
    position_gbp = 10_000.0
    position_native_usd = position_gbp / fx  # = 12_500

    cfg = SimConfig(n_paths=10_000, horizon_hours=1, spot=50.0,
                    sigma_hourly=0.01, drift_hourly=0.0, seed=3)
    result = simulate_price_paths(cfg)
    pnl_native = pnl_from_paths(result, direction_sign=1.0,
                                position_native=position_native_usd, position_unit="GBP")
    pnl_gbp = pnl_native * fx

    # Expected std of P&L in GBP: position_gbp × σ_h ≈ 10000 × 0.01 = 100.
    assert abs(pnl_gbp.std(ddof=0) - 100.0) < 8.0


def test_max_drawdown_is_non_negative() -> None:
    cfg = SimConfig(n_paths=2000, horizon_hours=24, spot=100.0,
                    sigma_hourly=0.05, drift_hourly=0.0, seed=99)
    result = simulate_price_paths(cfg)
    dd = empirical_max_drawdown(result, direction_sign=1.0,
                                position_native=10_000.0, position_unit="GBP", fx_to_gbp=1.0)
    assert dd >= 0
