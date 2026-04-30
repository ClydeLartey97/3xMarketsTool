"""Phase-1.1 tests: predict_distribution emits a true 95% band + sigma_price."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecasting.model import GradientBoostingForecastModel, _Z95


def _make_frame(n: int = 240, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    hours = np.arange(n)
    base = 50 + 10 * np.sin(hours * 2 * np.pi / 24)
    noise = rng.normal(0.0, 10.0, size=n)
    prices = base + noise

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "price_value": prices,
            "hour": hours % 24,
            "day_of_week": (hours // 24) % 7,
            "temperature_c": 12.0 + rng.normal(0, 2, n),
            "wind_speed": np.clip(rng.normal(7, 3, n), 0.5, None),
            "wind_generation_estimate": np.clip(rng.normal(4000, 1500, n), 0, None),
            "solar_generation_estimate": np.clip(rng.normal(800, 600, n), 0, None),
            "precipitation": np.clip(rng.exponential(0.2, n), 0, None),
            "demand_mw": 30000 + rng.normal(0, 2000, n),
            "demand_change": rng.normal(0, 200, n),
            "price_lag_1": np.r_[prices[0], prices[:-1]],
            "price_lag_24": np.r_[prices[:24], prices[:-24]],
            "rolling_mean_24": pd.Series(prices).rolling(24, min_periods=1).mean().to_numpy(),
            "rolling_std_24": pd.Series(prices).rolling(24, min_periods=1).std().fillna(8.0).to_numpy(),
            "event_count": np.zeros(n),
            "event_severity": np.zeros(n),
            "event_impact": np.zeros(n),
            "wind_to_demand_ratio": rng.uniform(0.05, 0.4, n),
            "solar_to_demand_ratio": rng.uniform(0.0, 0.2, n),
            "net_load_mw": 25000 + rng.normal(0, 1500, n),
            "net_load_change": rng.normal(0, 200, n),
            "renewable_share": rng.uniform(0.1, 0.6, n),
            "scarcity_index": rng.uniform(0.4, 0.9, n),
            "forecast_step": np.zeros(n),
        }
    )
    return frame


def test_band_is_95_percent_at_step_zero() -> None:
    frame = _make_frame()
    model = GradientBoostingForecastModel()
    model.train(frame)

    head = frame.tail(5).copy()
    head["forecast_step"] = 0
    dist = model.predict_distribution(head)

    half_widths = (dist["upper_bound"] - dist["point_estimate"]).to_numpy()
    sigmas = dist["sigma_price"].to_numpy()
    ratios = half_widths / sigmas

    # At step=0 the band must equal _Z95 * sigma exactly.
    assert np.allclose(ratios, _Z95, atol=1e-6)


def test_sigma_grows_with_horizon_step() -> None:
    frame = _make_frame()
    model = GradientBoostingForecastModel()
    model.train(frame)

    head = frame.tail(1).copy()
    sigmas = []
    for step in (0, 6, 12, 24):
        row = head.copy()
        row["forecast_step"] = step
        sigmas.append(float(model.predict_distribution(row)["sigma_price"].iloc[0]))

    # σ must be monotonically non-decreasing in horizon step.
    assert sigmas == sorted(sigmas)
    assert sigmas[-1] > sigmas[0]


def test_sigma_price_is_persisted_in_snapshot(db_session) -> None:
    """The forecast service should now write sigma_price into the snapshot."""
    from sqlalchemy import select

    from app.models import Market
    from app.services.forecast_service import run_forecast_for_market

    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    forecasts, _ = run_forecast_for_market(db_session, market, horizon_hours=6)

    assert forecasts, "expected forecasts to be produced"
    for f in forecasts:
        snap = f.feature_snapshot_json or {}
        assert "sigma_price" in snap, "sigma_price missing from forecast snapshot"
        assert snap["sigma_price"] > 0
