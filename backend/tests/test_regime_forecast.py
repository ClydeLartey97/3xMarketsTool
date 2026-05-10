from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecasting.backtest import _pit_histogram
from app.forecasting.model import GradientBoostingForecastModel
from app.forecasting.regime import REGIMES, classify_regime


def _regime_switching_frame(n: int = 900, seed: int = 23) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    hours = np.arange(n)
    regime_id = hours % len(REGIMES)
    true_sigma = np.choose(regime_id, [2.0, 9.0, 24.0])
    classifier_std = np.choose(regime_id, [7.0, 20.0, 45.0])
    seasonal = 80.0 + 7.0 * np.sin(hours * 2 * np.pi / 24)
    prices = seasonal + rng.normal(0.0, true_sigma, size=n)

    return pd.DataFrame(
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
            "rolling_mean_24": np.full(n, 100.0),
            "rolling_std_24": classifier_std,
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


def test_classify_regime_is_deterministic() -> None:
    row = pd.Series({"rolling_mean_24": 100.0, "rolling_std_24": 20.0, "event_impact": 0.0})

    assert classify_regime(row) == "trending"
    assert classify_regime(row.copy()) == classify_regime(row)


def test_per_regime_sigma_varies_when_regimes_have_samples() -> None:
    frame = _regime_switching_frame()
    model = GradientBoostingForecastModel()
    model.train(frame)

    sigmas = model.residual_std_by_regime
    assert set(sigmas) == set(REGIMES)
    assert sigmas["stressed"] > sigmas["calm"]
    assert len({round(value, 1) for value in sigmas.values()}) > 1

    dist = model.predict_distribution(frame.tail(9))
    assert set(dist["regime"]).issubset(set(REGIMES))
    assert len({round(value, 1) for value in dist["sigma_price"].to_numpy()}) > 1


def test_regime_sigma_improves_pit_uniformity_on_synthetic_switching_data() -> None:
    rng = np.random.default_rng(29)
    n = 6000
    regime_id = np.arange(n) % len(REGIMES)
    true_sigma = np.choose(regime_id, [2.0, 8.0, 18.0])
    mu = np.full(n, 50.0)
    actual = mu + true_sigma * rng.standard_normal(n)

    global_sigma = np.full(n, float(np.sqrt(np.mean(true_sigma**2))))
    global_pit = _pit_histogram(actual, mu, global_sigma, n_bins=10)
    regime_pit = _pit_histogram(actual, mu, true_sigma, n_bins=10)

    assert regime_pit["max_deviation_from_uniform"] < global_pit["max_deviation_from_uniform"]
    assert regime_pit["well_calibrated"] is True
