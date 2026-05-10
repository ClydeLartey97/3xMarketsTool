"""Phase-4 tests: walk-forward backtest framework."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.forecasting.backtest import (
    _baseline_climatology,
    _baseline_persistence,
    _baseline_persistence_24h,
    _pit_histogram,
    walk_forward_backtest,
)
from app.forecasting.registry import forecaster_registry


def _synth_frame(n: int = 24 * 90, seed: int = 11) -> pd.DataFrame:
    """A deterministic AR(1)-with-seasonality price series, with all the
    feature columns the backtest expects."""
    rng = np.random.default_rng(seed)
    hours = np.arange(n)
    seasonal = 50 + 10 * np.sin(hours * 2 * np.pi / 24) + 5 * np.sin(hours * 2 * np.pi / (24 * 7))
    noise = rng.normal(0, 4.0, size=n)
    prices = seasonal + noise

    rolling_mean = pd.Series(prices).rolling(24, min_periods=1).mean().to_numpy()
    rolling_std = pd.Series(prices).rolling(24, min_periods=1).std().fillna(4.0).to_numpy()

    frame = pd.DataFrame({
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
        "rolling_mean_24": rolling_mean,
        "rolling_std_24": rolling_std,
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
    })
    return frame


def test_walk_forward_runs_and_returns_metrics() -> None:
    frame = _synth_frame()
    result = walk_forward_backtest(
        frame, train_window_hours=24 * 30, test_window_hours=24 * 5,
        step_hours=24, horizon_hours=24,
    )
    assert result.sample_count > 0
    assert math.isfinite(result.metrics["rmse"])
    assert math.isfinite(result.metrics["mae"])
    assert 0.0 <= result.metrics["directional_accuracy"] <= 1.0
    # Calibration histogram present (shares are rounded to 4dp; tolerate that)
    assert result.calibration["n_bins"] == 10
    assert abs(sum(result.calibration["shares"]) - 1.0) < 1e-2
    # All baselines reported
    assert {"persistence", "persistence_24h", "climatology"} <= set(result.vs_baselines.keys())


def test_baselines_have_finite_rmse() -> None:
    frame = _synth_frame()
    pers = _baseline_persistence(frame, horizon=24)
    pers24 = _baseline_persistence_24h(frame, horizon=24)
    clim = _baseline_climatology(frame.iloc[: 24 * 30], frame.iloc[24 * 30 : 24 * 35])
    assert pers.size == frame.shape[0]
    assert pers24.size == frame.shape[0]
    assert clim.size == 24 * 5


def test_multi_forecaster_report_includes_gbr_and_chronos(monkeypatch) -> None:
    class FakeChronosForecastModel:
        model_name = "fake-chronos-v1"

        def train(self, frame: pd.DataFrame) -> dict[str, float]:
            return {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "spike_precision": 0.0}

        def predict(self, frame: pd.DataFrame) -> pd.Series:
            return frame["price_lag_24"].astype(float)

        def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
            preds = self.predict(frame)
            sigma = np.full(frame.shape[0], 5.0)
            return pd.DataFrame(
                {
                    "point_estimate": preds,
                    "lower_bound": preds - 8.0,
                    "upper_bound": preds + 8.0,
                    "sigma_price": sigma,
                },
                index=frame.index,
            )

        def explain(self, row: pd.Series) -> str:
            return "fake chronos"

    monkeypatch.setitem(forecaster_registry, "chronos", FakeChronosForecastModel)
    frame = _synth_frame(n=24 * 14)

    result = walk_forward_backtest(
        frame,
        train_window_hours=24 * 4,
        test_window_hours=24 * 2,
        step_hours=24 * 2,
        horizon_hours=24,
        forecaster_names=["gbr", "chronos"],
    )

    assert {"gbr", "chronos"} <= set(result.vs_forecasters)
    assert math.isfinite(result.vs_forecasters["gbr"]["rmse"])
    assert math.isfinite(result.vs_forecasters["chronos"]["rmse"])
    assert {"gbr", "chronos"} <= set(result.to_dict()["vs_forecasters"])


def test_pit_histogram_is_uniform_for_calibrated_input() -> None:
    """If predictions truly are mu + sigma·N(0,1), PIT should be ~uniform."""
    rng = np.random.default_rng(0)
    n = 5000
    mu = rng.uniform(40, 60, size=n)
    sigma = rng.uniform(2, 5, size=n)
    actual = mu + sigma * rng.standard_normal(n)
    cal = _pit_histogram(actual, mu, sigma, n_bins=10)
    # With 5k samples max deviation should be small but not exactly zero.
    assert cal["max_deviation_from_uniform"] < 0.04
    assert cal["well_calibrated"] is True


def test_overconfident_sigma_is_flagged() -> None:
    rng = np.random.default_rng(1)
    n = 2000
    mu = np.full(n, 50.0)
    truth = mu + 5.0 * rng.standard_normal(n)
    # Predict the same mean but claim sigma is tiny — should fail calibration.
    cal = _pit_histogram(truth, mu, np.full(n, 0.5), n_bins=10)
    assert cal["well_calibrated"] is False
    assert cal["max_deviation_from_uniform"] > 0.05
