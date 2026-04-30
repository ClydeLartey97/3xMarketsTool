from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.forecasting.base import ForecastModel


# Standard normal one-sided 95% quantile.
_Z95 = 1.6449


FEATURE_COLUMNS = [
    "hour",
    "day_of_week",
    "temperature_c",
    "wind_speed",
    "wind_generation_estimate",
    "solar_generation_estimate",
    "precipitation",
    "demand_mw",
    "demand_change",
    "price_lag_1",
    "price_lag_24",
    "rolling_mean_24",
    "rolling_std_24",
    "event_count",
    "event_severity",
    "event_impact",
    "wind_to_demand_ratio",
    "solar_to_demand_ratio",
    "net_load_mw",
    "net_load_change",
    "renewable_share",
    "scarcity_index",
    "forecast_step",
]


class GradientBoostingForecastModel(ForecastModel):
    def __init__(self) -> None:
        self.model = GradientBoostingRegressor(random_state=42)
        self.residual_std = 12.0
        self.metrics: dict[str, float] = {}
        self.model_name = "hybrid-signal-v3"

    def _composite_signal(self, frame: pd.DataFrame, model_pred: np.ndarray | pd.Series) -> np.ndarray:
        baseline = (
            0.48 * np.asarray(model_pred)
            + 0.24 * frame["price_lag_24"].to_numpy()
            + 0.18 * frame["rolling_mean_24"].to_numpy()
            + 0.10 * frame["price_lag_1"].to_numpy()
        )
        demand_push = np.clip(frame["demand_change"].to_numpy() / 320.0, -6.0, 6.0)
        renewable_drag = np.clip((0.28 - frame["renewable_share"].to_numpy()) * 26.0, -5.0, 8.0)
        event_shock = np.clip(
            (frame["event_impact"].to_numpy() * 1.7) + (frame["event_severity"].to_numpy() * 0.65),
            -8.0,
            12.0,
        )
        net_load_pressure = np.clip(frame["net_load_change"].to_numpy() / 450.0, -5.0, 6.0)
        scarcity = np.clip((frame["scarcity_index"].to_numpy() - 0.72) * 28.0, -4.0, 8.0)
        intraday_regime = np.clip(
            (frame["price_lag_1"].to_numpy() - frame["rolling_mean_24"].to_numpy()) * 0.18,
            -6.0,
            6.0,
        )
        return baseline + demand_push + renewable_drag + event_shock + net_load_pressure + scarcity + intraday_regime

    def train(self, frame: pd.DataFrame) -> dict[str, float]:
        split_idx = max(int(len(frame) * 0.8), 48)
        train_frame = frame.iloc[:split_idx]
        test_frame = frame.iloc[split_idx:]

        self.model.fit(train_frame[FEATURE_COLUMNS], train_frame["price_value"])
        if not test_frame.empty:
            model_preds = self.model.predict(test_frame[FEATURE_COLUMNS])
            preds = self._composite_signal(test_frame, model_preds)
            residuals = test_frame["price_value"] - preds
            self.residual_std = float(max(residuals.std(ddof=0), 4.0))
            direction = ((preds - test_frame["price_lag_1"]) > 0) == ((test_frame["price_value"] - test_frame["price_lag_1"]) > 0)
            actual_spike = test_frame["price_value"] > (
                test_frame["rolling_mean_24"] + (1.4 * test_frame["rolling_std_24"].clip(lower=8.0))
            )
            predicted_spike = preds > (
                test_frame["rolling_mean_24"] + (1.25 * test_frame["rolling_std_24"].clip(lower=8.0))
            )
            true_positive = float((actual_spike & predicted_spike).sum())
            predicted_positive = float(predicted_spike.sum())
            self.metrics = {
                "mae": round(float(mean_absolute_error(test_frame["price_value"], preds)), 2),
                "rmse": round(float(math.sqrt(mean_squared_error(test_frame["price_value"], preds))), 2),
                "directional_accuracy": round(float(direction.mean()), 3),
                "spike_precision": round(true_positive / predicted_positive, 3) if predicted_positive else 0.0,
            }
        else:
            self.metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "spike_precision": 0.0}
        return self.metrics

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        model_pred = self.model.predict(frame[FEATURE_COLUMNS])
        return pd.Series(self._composite_signal(frame, model_pred), index=frame.index)

    def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
        preds = self.predict(frame)
        horizon_scale = 1.0 + frame["forecast_step"].fillna(0.0).clip(lower=0.0).to_numpy() / 18.0
        sigma = self.residual_std * horizon_scale
        band_width = _Z95 * sigma
        return pd.DataFrame(
            {
                "point_estimate": preds,
                "lower_bound": preds - band_width,
                "upper_bound": preds + band_width,
                "sigma_price": sigma,
            },
            index=frame.index,
        )

    def explain(self, row: pd.Series) -> str:
        drivers: list[str] = []
        if row["demand_mw"] > row["rolling_mean_24"] * 1.02:
            drivers.append("demand is running above the recent 24-hour curve")
        if row["renewable_share"] < 0.2:
            drivers.append("renewable share is thin for this hour")
        if row["event_impact"] > 0.8:
            drivers.append("a structured event shock is still embedded in the curve")
        if row["temperature_c"] > 30:
            drivers.append("temperature is lifting cooling load")
        if row["price_lag_1"] > row["price_lag_24"] + 8:
            drivers.append("the intraday regime is tighter than yesterday's hour")
        if not drivers:
            drivers.append("the day-ago anchor and current intraday balance are aligned")
        return "Hybrid signal is anchored to the day-ago hour, then adjusted for " + ", ".join(drivers[:3]) + "."
