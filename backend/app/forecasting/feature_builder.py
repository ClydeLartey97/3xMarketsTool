from __future__ import annotations

import pandas as pd


def build_feature_frame(
    prices: pd.DataFrame,
    weather: pd.DataFrame,
    demand: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    frame = prices.merge(weather, on="timestamp", how="left").merge(demand, on="timestamp", how="left")
    if not events.empty:
        event_features = (
            events.groupby("timestamp")
            .agg(
                event_count=("severity_score", "sum"),
                event_severity=("severity_score", "max"),
                event_impact=("impact_pct", "sum"),
            )
            .reset_index()
        )
        frame = frame.merge(event_features, on="timestamp", how="left")
    else:
        frame["event_count"] = 0.0
        frame["event_severity"] = 0.0
        frame["event_impact"] = 0.0

    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["hour"] = frame["timestamp"].dt.hour
    frame["day_of_week"] = frame["timestamp"].dt.dayofweek
    frame["price_lag_1"] = frame["price_value"].shift(1)
    frame["price_lag_24"] = frame["price_value"].shift(24)
    frame["rolling_mean_24"] = frame["price_value"].rolling(24, min_periods=1).mean()
    frame["rolling_std_24"] = frame["price_value"].rolling(24, min_periods=1).std().fillna(0.0)
    frame["demand_change"] = frame["demand_mw"].diff().fillna(0.0)
    frame["wind_to_demand_ratio"] = frame["wind_generation_estimate"] / frame["demand_mw"].replace(0, 1)
    frame["solar_to_demand_ratio"] = frame["solar_generation_estimate"] / frame["demand_mw"].replace(0, 1)

    frame["event_count"] = frame["event_count"].fillna(0.0)
    frame["event_severity"] = frame["event_severity"].fillna(0.0)
    frame["event_impact"] = frame["event_impact"].fillna(0.0)

    return frame.dropna().reset_index(drop=True)
