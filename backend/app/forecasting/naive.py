from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecasting.base import ForecastModel
from app.forecasting.regime import classify_regime
from app.forecasting.model import _Z95


class NaivePersistence24hForecastModel(ForecastModel):
    def __init__(self) -> None:
        self.model_name = "naive-persistence-24h-v1"
        self.residual_std = 12.0
        self.metrics: dict[str, float] = {}

    def train(self, frame: pd.DataFrame) -> dict[str, float]:
        if frame.empty or "price_value" not in frame.columns or "price_lag_24" not in frame.columns:
            self.metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "spike_precision": 0.0}
            return self.metrics

        preds = frame["price_lag_24"].astype(float)
        actual = frame["price_value"].astype(float)
        residuals = actual - preds
        self.residual_std = float(max(residuals.std(ddof=0), 4.0))
        baseline_prev = frame["price_lag_1"].astype(float)
        direction = ((preds - baseline_prev) > 0) == ((actual - baseline_prev) > 0)
        self.metrics = {
            "mae": round(float(np.mean(np.abs(residuals))), 2),
            "rmse": round(float(np.sqrt(np.mean(np.square(residuals)))), 2),
            "directional_accuracy": round(float(direction.mean()), 3),
            "spike_precision": 0.0,
        }
        return self.metrics

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        if "price_lag_24" in frame.columns:
            return frame["price_lag_24"].astype(float)
        return frame["price_lag_1"].astype(float)

    def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
        preds = self.predict(frame)
        horizon_scale = 1.0 + frame["forecast_step"].fillna(0.0).clip(lower=0.0).to_numpy() / 18.0
        sigma = self.residual_std * horizon_scale
        band_width = _Z95 * sigma
        regimes = frame.apply(classify_regime, axis=1)
        return pd.DataFrame(
            {
                "point_estimate": preds,
                "lower_bound": preds - band_width,
                "upper_bound": preds + band_width,
                "sigma_price": sigma,
                "regime": regimes.to_numpy(),
            },
            index=frame.index,
        )

    def explain(self, row: pd.Series) -> str:
        return "Naive persistence anchors the forecast to yesterday's same hour."
