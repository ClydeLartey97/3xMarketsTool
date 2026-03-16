from __future__ import annotations

import math

import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.forecasting.base import ForecastModel


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
]


class GradientBoostingForecastModel(ForecastModel):
    def __init__(self) -> None:
        self.model = GradientBoostingRegressor(random_state=42)
        self.residual_std = 12.0
        self.metrics: dict[str, float] = {}

    def train(self, frame: pd.DataFrame) -> dict[str, float]:
        split_idx = max(int(len(frame) * 0.8), 48)
        train_frame = frame.iloc[:split_idx]
        test_frame = frame.iloc[split_idx:]

        self.model.fit(train_frame[FEATURE_COLUMNS], train_frame["price_value"])
        if not test_frame.empty:
            preds = self.model.predict(test_frame[FEATURE_COLUMNS])
            residuals = test_frame["price_value"] - preds
            self.residual_std = float(max(residuals.std(ddof=0), 4.0))
            direction = ((preds - test_frame["price_lag_1"]) > 0) == ((test_frame["price_value"] - test_frame["price_lag_1"]) > 0)
            self.metrics = {
                "mae": round(float(mean_absolute_error(test_frame["price_value"], preds)), 2),
                "rmse": round(float(math.sqrt(mean_squared_error(test_frame["price_value"], preds))), 2),
                "directional_accuracy": round(float(direction.mean()), 3),
            }
        else:
            self.metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0}
        return self.metrics

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        return pd.Series(self.model.predict(frame[FEATURE_COLUMNS]), index=frame.index)

    def predict_distribution(self, frame: pd.DataFrame) -> pd.DataFrame:
        preds = self.predict(frame)
        return pd.DataFrame(
            {
                "point_estimate": preds,
                "lower_bound": preds - (1.28 * self.residual_std),
                "upper_bound": preds + (1.28 * self.residual_std),
            },
            index=frame.index,
        )

    def explain(self, row: pd.Series) -> str:
        drivers: list[str] = []
        if row["demand_mw"] > 47000:
            drivers.append("elevated demand")
        if row["wind_generation_estimate"] < 6000:
            drivers.append("reduced wind output")
        if row["event_impact"] > 1:
            drivers.append("recent grid events")
        if row["temperature_c"] > 31:
            drivers.append("heat-driven load")
        if row["solar_generation_estimate"] < 2500 and row["hour"] >= 18:
            drivers.append("weaker evening solar")
        if not drivers:
            drivers.append("normal intraday seasonality")
        return "Forecast is shaped by " + ", ".join(drivers[:3]) + "."
