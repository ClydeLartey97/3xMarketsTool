"""Walk-forward backtesting framework for the price forecaster.

Implements PLAN.md § Phase 4. Produces a structured `BacktestResult` with:

  - aggregate metrics (MAE, RMSE, directional accuracy, spike P/R/F1)
  - hour-of-day breakdown
  - regime breakdown
  - PIT calibration histogram
  - vs baseline benchmarks (persistence, persistence_24h, climatology)

Designed to be cheap enough to run nightly per market, while still being
the gate that proves the model is worth using.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import math
import numpy as np
import pandas as pd

from app.forecasting.feature_builder import build_feature_frame
from app.forecasting.model import FEATURE_COLUMNS, GradientBoostingForecastModel


# ── Result schemas ────────────────────────────────────────────────────────


@dataclass
class BacktestResult:
    metrics: dict[str, float]
    metrics_by_hour: dict[int, dict[str, float]]
    metrics_by_regime: dict[str, dict[str, float]]
    calibration: dict[str, Any]
    vs_baselines: dict[str, dict[str, float]]
    sample_count: int
    horizon_hours: int
    train_window_hours: int
    test_window_hours: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "metrics_by_hour": {str(k): v for k, v in self.metrics_by_hour.items()},
            "metrics_by_regime": self.metrics_by_regime,
            "calibration": self.calibration,
            "vs_baselines": self.vs_baselines,
            "sample_count": self.sample_count,
            "horizon_hours": self.horizon_hours,
            "train_window_hours": self.train_window_hours,
            "test_window_hours": self.test_window_hours,
        }


# ── Helpers ───────────────────────────────────────────────────────────────


def _classify_regime(row: pd.Series) -> str:
    rolling_std = float(row.get("rolling_std_24", 0.0) or 0.0)
    rolling_mean = float(row.get("rolling_mean_24", 0.0) or 0.0)
    event_impact = float(row.get("event_impact", 0.0) or 0.0)
    if rolling_mean <= 0:
        return "calm"
    cv = rolling_std / max(rolling_mean, 1.0)
    if cv > 0.35 or event_impact > 1.0:
        return "stressed"
    if cv > 0.15:
        return "trending"
    return "calm"


def _is_spike(values: np.ndarray, mean: np.ndarray, std: np.ndarray, k: float = 2.0) -> np.ndarray:
    return values > (mean + k * np.maximum(std, 1.0))


def _safe_ratio(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return float(num) / float(den)


def _accuracy_metrics(actual: np.ndarray, pred: np.ndarray, baseline_prev: np.ndarray) -> dict[str, float]:
    if actual.size == 0:
        return {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0}
    diff = actual - pred
    mae = float(np.mean(np.abs(diff)))
    rmse = float(math.sqrt(float(np.mean(diff * diff))))
    actual_dir = np.sign(actual - baseline_prev)
    pred_dir = np.sign(pred - baseline_prev)
    matches = (actual_dir == pred_dir).astype(float)
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "directional_accuracy": round(float(matches.mean()), 4),
    }


def _spike_metrics(actual_spike: np.ndarray, pred_spike: np.ndarray) -> dict[str, float]:
    tp = float(np.sum(actual_spike & pred_spike))
    fp = float(np.sum(~actual_spike & pred_spike))
    fn = float(np.sum(actual_spike & ~pred_spike))
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _safe_ratio(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    return {
        "spike_precision": round(precision, 4),
        "spike_recall": round(recall, 4),
        "spike_f1": round(f1, 4),
    }


def _pit_histogram(actual: np.ndarray, mu: np.ndarray, sigma: np.ndarray, n_bins: int = 10) -> dict[str, Any]:
    """Probability integral transform — uniform if calibration is perfect."""
    safe_sigma = np.maximum(sigma, 1e-6)
    z = (actual - mu) / safe_sigma
    # Standard normal CDF via erf
    pit_values = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
    counts, edges = np.histogram(pit_values, bins=n_bins, range=(0.0, 1.0))
    shares = (counts / max(counts.sum(), 1)).tolist()
    expected = 1.0 / n_bins
    max_dev = float(max(abs(s - expected) for s in shares)) if shares else 0.0
    return {
        "n_bins": n_bins,
        "shares": [round(s, 4) for s in shares],
        "expected_share_per_bin": round(expected, 4),
        "max_deviation_from_uniform": round(max_dev, 4),
        "well_calibrated": max_dev <= 0.05,
    }


# ── Baselines ─────────────────────────────────────────────────────────────


def _baseline_persistence(frame: pd.DataFrame, horizon: int) -> np.ndarray:
    """ŷ_{t+h} = y_t — just the last observed price."""
    return frame["price_lag_1"].to_numpy()


def _baseline_persistence_24h(frame: pd.DataFrame, horizon: int) -> np.ndarray:
    """ŷ_{t+h} = y_{t-(24-h)} — yesterday's same hour."""
    return frame["price_lag_24"].to_numpy()


def _baseline_climatology(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Mean by (hour, day_of_week) over the training window."""
    grouped = train.groupby(["hour", "day_of_week"])["price_value"].mean()
    keys = list(zip(test["hour"].to_numpy().astype(int), test["day_of_week"].to_numpy().astype(int)))
    fallback = float(train["price_value"].mean()) if not train["price_value"].empty else 0.0
    out = np.array([grouped.get((h, d), fallback) for h, d in keys], dtype=float)
    return out


# ── Core walk-forward driver ──────────────────────────────────────────────


def walk_forward_backtest(
    feature_frame: pd.DataFrame,
    *,
    train_window_hours: int = 24 * 60,
    test_window_hours: int = 24 * 7,
    step_hours: int = 24,
    horizon_hours: int = 24,
    spike_k: float = 2.0,
) -> BacktestResult:
    """Roll a (train_window, test_window) pair across the frame.

    The model is re-fit at every step. Baselines do not need fitting.
    """
    if feature_frame.empty or "price_value" not in feature_frame.columns:
        return BacktestResult(
            metrics={"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0,
                     "spike_precision": 0.0, "spike_recall": 0.0, "spike_f1": 0.0},
            metrics_by_hour={},
            metrics_by_regime={},
            calibration={"n_bins": 0, "shares": [], "expected_share_per_bin": 0.0,
                         "max_deviation_from_uniform": 0.0, "well_calibrated": False},
            vs_baselines={},
            sample_count=0,
            horizon_hours=horizon_hours,
            train_window_hours=train_window_hours,
            test_window_hours=test_window_hours,
        )

    n = len(feature_frame)
    rows = feature_frame.reset_index(drop=True).copy()
    needed = train_window_hours + test_window_hours

    pred_records: list[pd.DataFrame] = []
    starts = list(range(0, max(0, n - needed) + 1, max(step_hours, 1)))
    if not starts:
        starts = [0] if n >= needed else []

    for start in starts:
        train = rows.iloc[start : start + train_window_hours]
        test = rows.iloc[start + train_window_hours : start + needed].copy()
        if len(train) < 48 or len(test) == 0:
            continue
        try:
            model = GradientBoostingForecastModel()
            model.train(train)
            preds = model.predict(test).to_numpy()
            sigmas = np.full_like(preds, model.residual_std, dtype=float)
        except Exception:  # noqa: BLE001 — keep walking on any single-fit failure
            continue
        test = test.copy()
        test["pred"] = preds
        test["sigma_pred"] = sigmas
        test["regime"] = test.apply(_classify_regime, axis=1)
        pred_records.append(test)

    if not pred_records:
        return BacktestResult(
            metrics={"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0,
                     "spike_precision": 0.0, "spike_recall": 0.0, "spike_f1": 0.0},
            metrics_by_hour={},
            metrics_by_regime={},
            calibration={"n_bins": 0, "shares": [], "expected_share_per_bin": 0.0,
                         "max_deviation_from_uniform": 0.0, "well_calibrated": False},
            vs_baselines={},
            sample_count=0,
            horizon_hours=horizon_hours,
            train_window_hours=train_window_hours,
            test_window_hours=test_window_hours,
        )

    combined = pd.concat(pred_records, ignore_index=True)
    actual = combined["price_value"].to_numpy()
    pred = combined["pred"].to_numpy()
    sigma_pred = combined["sigma_pred"].to_numpy()
    baseline_prev = combined["price_lag_1"].to_numpy()
    rolling_mean = combined["rolling_mean_24"].to_numpy()
    rolling_std = combined["rolling_std_24"].to_numpy()

    metrics = _accuracy_metrics(actual, pred, baseline_prev)
    actual_spike = _is_spike(actual, rolling_mean, rolling_std, k=spike_k)
    pred_spike = _is_spike(pred, rolling_mean, rolling_std, k=spike_k * 0.85)
    metrics.update(_spike_metrics(actual_spike, pred_spike))

    # Hour-of-day breakdown
    by_hour: dict[int, dict[str, float]] = {}
    for hour, frame in combined.groupby("hour"):
        by_hour[int(hour)] = _accuracy_metrics(
            frame["price_value"].to_numpy(),
            frame["pred"].to_numpy(),
            frame["price_lag_1"].to_numpy(),
        )

    # Regime breakdown
    by_regime: dict[str, dict[str, float]] = {}
    for regime, frame in combined.groupby("regime"):
        by_regime[str(regime)] = _accuracy_metrics(
            frame["price_value"].to_numpy(),
            frame["pred"].to_numpy(),
            frame["price_lag_1"].to_numpy(),
        )

    # Calibration
    calibration = _pit_histogram(actual, pred, sigma_pred)

    # Baselines
    persistence_pred = _baseline_persistence(combined, horizon_hours)
    persistence_24_pred = _baseline_persistence_24h(combined, horizon_hours)
    # For climatology we need a 'training' window aligned to each prediction
    # — approximate with the first training window for cheapness.
    first_train = rows.iloc[: train_window_hours]
    clim_pred = _baseline_climatology(first_train, combined)

    vs_baselines: dict[str, dict[str, float]] = {
        "persistence": _accuracy_metrics(actual, persistence_pred, baseline_prev),
        "persistence_24h": _accuracy_metrics(actual, persistence_24_pred, baseline_prev),
        "climatology": _accuracy_metrics(actual, clim_pred, baseline_prev),
    }

    return BacktestResult(
        metrics=metrics,
        metrics_by_hour=by_hour,
        metrics_by_regime=by_regime,
        calibration=calibration,
        vs_baselines=vs_baselines,
        sample_count=int(combined.shape[0]),
        horizon_hours=horizon_hours,
        train_window_hours=train_window_hours,
        test_window_hours=test_window_hours,
    )


# ── Convenience runner: build feature frame from raw db rows ──────────────


def build_feature_frame_from_db(
    *,
    prices: list[Any],
    weather: list[Any],
    demand: list[Any],
    events_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Mirror of the production feature builder, exposed for the runner."""
    def _to_df(records: list[Any]) -> pd.DataFrame:
        rows = []
        for r in records:
            data = r.__dict__.copy()
            data.pop("_sa_instance_state", None)
            rows.append(data)
        return pd.DataFrame(rows)

    price_df = _to_df(prices)
    weather_df = _to_df(weather)
    demand_df = _to_df(demand)
    return build_feature_frame(price_df, weather_df, demand_df, events_frame)
