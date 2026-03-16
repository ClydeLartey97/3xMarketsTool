from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.forecasting.feature_builder import build_feature_frame
from app.forecasting.model import FEATURE_COLUMNS, GradientBoostingForecastModel
from app.models import DemandPoint, Event, Forecast, Market, PricePoint, WeatherPoint
from app.services.event_service import events_as_feature_frame


def _to_dataframe(records: list, mapping: dict[str, str] | None = None) -> pd.DataFrame:
    rows = []
    for record in records:
        data = record.__dict__.copy()
        data.pop("_sa_instance_state", None)
        rows.append(data)
    frame = pd.DataFrame(rows)
    if mapping and not frame.empty:
        frame = frame.rename(columns=mapping)
    return frame


def list_recent_prices(db: Session, market_id: int, limit: int = 168) -> list[PricePoint]:
    stmt = (
        select(PricePoint)
        .where(PricePoint.market_id == market_id)
        .order_by(desc(PricePoint.timestamp))
        .limit(limit)
    )
    return list(reversed(list(db.scalars(stmt).all())))


def list_forecasts(db: Session, market_id: int, limit: int = 24) -> list[Forecast]:
    stmt = (
        select(Forecast)
        .where(Forecast.market_id == market_id)
        .order_by(Forecast.forecast_for_timestamp.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def run_forecast_for_market(db: Session, market: Market, horizon_hours: int = 24) -> tuple[list[Forecast], dict[str, float]]:
    prices = list(
        db.scalars(
            select(PricePoint).where(PricePoint.market_id == market.id).order_by(PricePoint.timestamp.asc())
        ).all()
    )
    weather = list(
        db.scalars(
            select(WeatherPoint).where(WeatherPoint.market_id == market.id).order_by(WeatherPoint.timestamp.asc())
        ).all()
    )
    demand = list(
        db.scalars(
            select(DemandPoint).where(DemandPoint.market_id == market.id).order_by(DemandPoint.timestamp.asc())
        ).all()
    )
    events = list(
        db.scalars(select(Event).where(Event.market_id == market.id).order_by(Event.created_at.asc())).all()
    )

    price_df = _to_dataframe(prices)
    weather_df = _to_dataframe(weather)
    demand_df = _to_dataframe(demand)
    events_df = pd.DataFrame(events_as_feature_frame(events))

    if price_df.empty or weather_df.empty or demand_df.empty:
        return [], {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0}

    feature_frame = build_feature_frame(price_df, weather_df, demand_df, events_df)
    model = GradientBoostingForecastModel()
    metrics = model.train(feature_frame)

    latest = feature_frame.iloc[-1].copy()
    latest_timestamp = pd.Timestamp(latest["timestamp"])
    future_rows = []
    rolling_price = float(latest["price_value"])
    for step in range(1, horizon_hours + 1):
        row = latest.copy()
        forecast_ts = latest_timestamp + pd.Timedelta(hours=step)
        row["timestamp"] = forecast_ts
        row["hour"] = forecast_ts.hour
        row["day_of_week"] = forecast_ts.day_of_week
        row["temperature_c"] = float(latest["temperature_c"]) + (1.2 if 14 <= forecast_ts.hour <= 18 else -0.4)
        row["wind_generation_estimate"] = max(1200.0, float(latest["wind_generation_estimate"]) + (-180 if 17 <= forecast_ts.hour <= 21 else 90))
        row["solar_generation_estimate"] = max(0.0, 3800.0 if 9 <= forecast_ts.hour <= 16 else 250.0 if 17 <= forecast_ts.hour <= 18 else 0.0)
        row["demand_mw"] = max(26000.0, float(latest["demand_mw"]) + (1400 if 17 <= forecast_ts.hour <= 21 else -350))
        row["demand_change"] = row["demand_mw"] - float(latest["demand_mw"])
        row["price_lag_1"] = rolling_price
        row["price_lag_24"] = float(latest["price_lag_24"])
        row["rolling_mean_24"] = float(latest["rolling_mean_24"])
        row["rolling_std_24"] = float(latest["rolling_std_24"])
        row["event_count"] = float(latest["event_count"])
        row["event_severity"] = float(latest["event_severity"])
        row["event_impact"] = float(latest["event_impact"])
        row["wind_to_demand_ratio"] = row["wind_generation_estimate"] / row["demand_mw"]
        row["solar_to_demand_ratio"] = row["solar_generation_estimate"] / row["demand_mw"]
        future_rows.append(row)

    future_frame = pd.DataFrame(future_rows).reset_index(drop=True)
    distributions = model.predict_distribution(future_frame)

    db.execute(delete(Forecast).where(Forecast.market_id == market.id))
    db.flush()

    forecasts: list[Forecast] = []
    for idx, row in future_frame.iterrows():
        dist = distributions.iloc[idx]
        point_estimate = float(dist["point_estimate"])
        rolling_price = point_estimate
        spike_probability = min(
            0.95,
            max(
                0.05,
                ((point_estimate - float(row["rolling_mean_24"])) / max(float(row["rolling_std_24"]), 8.0)) * 0.12 + 0.18,
            ),
        )
        forecast = Forecast(
            market_id=market.id,
            forecast_for_timestamp=row["timestamp"].to_pydatetime(),
            point_estimate=round(point_estimate, 2),
            lower_bound=round(float(dist["lower_bound"]), 2),
            upper_bound=round(float(dist["upper_bound"]), 2),
            spike_probability=round(float(spike_probability), 3),
            model_version="gbr-v1",
            rationale_summary=model.explain(row),
            feature_snapshot_json={key: round(float(row[key]), 4) for key in FEATURE_COLUMNS if key in row},
        )
        db.add(forecast)
        forecasts.append(forecast)

    db.commit()
    for forecast in forecasts:
        db.refresh(forecast)
    return forecasts, metrics
