from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.forecasting.feature_builder import build_feature_frame
from app.forecasting.model import FEATURE_COLUMNS, GradientBoostingForecastModel, _Z95
from app.ingestion.real_data import market_currency
from app.models import DemandPoint, Event, Forecast, Market, PricePoint, WeatherPoint
from app.services.event_service import events_as_feature_frame

# ── In-process forecast cache (15-minute TTL) ─────────────────────────────────
_forecast_cache: dict[str, tuple[list[Forecast], dict[str, float], datetime]] = {}
_CACHE_TTL_MINUTES = 15


def _cache_get(market_code: str, horizon_hours: int) -> tuple[list[Forecast], dict[str, float]] | None:
    entry = _forecast_cache.get(market_code)
    if entry:
        forecasts, metrics, cached_at = entry
        if (
            datetime.now(timezone.utc) - cached_at < timedelta(minutes=_CACHE_TTL_MINUTES)
            and len(forecasts) >= horizon_hours
        ):
            return forecasts[:horizon_hours], metrics
    return None


def _cache_set(market_code: str, forecasts: list[Forecast], metrics: dict[str, float]) -> None:
    _forecast_cache[market_code] = (forecasts, metrics, datetime.now(timezone.utc))


def invalidate_forecast_cache(market_code: str | None = None) -> None:
    if market_code:
        _forecast_cache.pop(market_code, None)
    else:
        _forecast_cache.clear()


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


def list_price_history(
    db: Session,
    market_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[PricePoint]:
    stmt = select(PricePoint).where(PricePoint.market_id == market_id)
    if start is not None:
        stmt = stmt.where(PricePoint.timestamp >= start)
    if end is not None:
        stmt = stmt.where(PricePoint.timestamp <= end)
    stmt = stmt.order_by(PricePoint.timestamp.asc())
    return list(db.scalars(stmt).all())


def list_forecasts(db: Session, market_id: int, limit: int = 48) -> list[Forecast]:
    stmt = (
        select(Forecast)
        .where(Forecast.market_id == market_id)
        .order_by(Forecast.forecast_for_timestamp.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def _hourly_anchor(frame: pd.DataFrame, column: str, hour: int, fallback: float) -> float:
    same_hour = frame.loc[frame["hour"] == hour, column].tail(5)
    if same_hour.empty:
        return float(fallback)
    return float(same_hour.mean())


def _hourly_regime_anchor(frame: pd.DataFrame, column: str, hour: int, day_of_week: int, fallback: float) -> float:
    same_hour = frame.loc[frame["hour"] == hour, column].tail(12)
    same_slot = frame.loc[(frame["hour"] == hour) & (frame["day_of_week"] == day_of_week), column].tail(4)
    weighted_values: list[tuple[float, float]] = []
    if not same_hour.empty:
        weighted_values.append((0.65, float(same_hour.mean())))
    if not same_slot.empty:
        weighted_values.append((0.35, float(same_slot.mean())))
    if not weighted_values:
        return float(fallback)
    weight_sum = sum(weight for weight, _ in weighted_values)
    return sum(weight * value for weight, value in weighted_values) / weight_sum


def _linear_sensitivity(x: pd.Series, y: pd.Series, scale: float = 1.0, clip: tuple[float, float] = (-12.0, 12.0)) -> float:
    if len(x) < 3:
        return 0.0
    x_std = float(x.std(ddof=0))
    if x_std < 1e-6:
        return 0.0
    slope = float(np.polyfit(x.to_numpy(), y.to_numpy(), 1)[0]) * scale
    return float(np.clip(slope, clip[0], clip[1]))


def _market_signature(frame: pd.DataFrame) -> dict[str, object]:
    recent = frame.tail(min(len(frame), 168)).copy()
    return {
        "mean_price": float(recent["price_value"].mean()),
        "mean_scarcity": float(recent["scarcity_index"].mean()),
        "hourly_price": recent.groupby("hour")["price_value"].mean().to_dict(),
        "dow_price": recent.groupby("day_of_week")["price_value"].mean().to_dict(),
        "hourly_demand": recent.groupby("hour")["demand_mw"].mean().to_dict(),
        "hourly_wind": recent.groupby("hour")["wind_generation_estimate"].mean().to_dict(),
        "hourly_solar": recent.groupby("hour")["solar_generation_estimate"].mean().to_dict(),
        "hourly_temp": recent.groupby("hour")["temperature_c"].mean().to_dict(),
        "demand_beta": _linear_sensitivity(recent["demand_mw"] / 1000.0, recent["price_value"]),
        "wind_beta": _linear_sensitivity(recent["wind_generation_estimate"] / 1000.0, recent["price_value"]),
        "solar_beta": _linear_sensitivity(recent["solar_generation_estimate"] / 1000.0, recent["price_value"]),
        "temp_beta": _linear_sensitivity(recent["temperature_c"], recent["price_value"], clip=(-4.0, 4.0)),
        "event_beta": _linear_sensitivity(recent["event_impact"], recent["price_value"], clip=(-8.0, 8.0)),
    }


def run_forecast_for_market(
    db: Session,
    market: Market,
    horizon_hours: int = 24,
    use_cache: bool = True,
) -> tuple[list[Forecast], dict[str, float]]:
    # Return cached result if still fresh
    if use_cache:
        cached = _cache_get(market.code, horizon_hours)
        if cached:
            forecasts, metrics = cached
            # Check DB still has these forecasts (could have been cleared)
            if forecasts and db.get(Forecast, forecasts[0].id):
                return forecasts, metrics

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
        return [], {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "spike_precision": 0.0}

    feature_frame = build_feature_frame(price_df, weather_df, demand_df, events_df)
    model = GradientBoostingForecastModel()
    metrics = model.train(feature_frame)
    market_signature = _market_signature(feature_frame)

    latest = feature_frame.iloc[-1].copy()
    latest_timestamp = pd.Timestamp(latest["timestamp"])
    rolling_price = float(latest["price_value"])
    projected_prices = feature_frame["price_value"].tail(24).astype(float).tolist()
    future_rows: list[pd.Series] = []
    current_demand_baseline = _hourly_regime_anchor(
        feature_frame,
        "demand_mw",
        int(latest["hour"]),
        int(latest["day_of_week"]),
        float(latest["demand_mw"]),
    )
    current_wind_baseline = _hourly_regime_anchor(
        feature_frame,
        "wind_generation_estimate",
        int(latest["hour"]),
        int(latest["day_of_week"]),
        float(latest["wind_generation_estimate"]),
    )
    current_solar_baseline = _hourly_regime_anchor(
        feature_frame,
        "solar_generation_estimate",
        int(latest["hour"]),
        int(latest["day_of_week"]),
        float(latest["solar_generation_estimate"]),
    )
    current_temp_baseline = _hourly_regime_anchor(
        feature_frame,
        "temperature_c",
        int(latest["hour"]),
        int(latest["day_of_week"]),
        float(latest["temperature_c"]),
    )
    demand_deviation = float(latest["demand_mw"]) - current_demand_baseline
    wind_deviation = float(latest["wind_generation_estimate"]) - current_wind_baseline
    solar_deviation = float(latest["solar_generation_estimate"]) - current_solar_baseline
    temp_deviation = float(latest["temperature_c"]) - current_temp_baseline

    db.execute(delete(Forecast).where(Forecast.market_id == market.id))
    db.flush()

    forecasts: list[Forecast] = []
    for step in range(1, horizon_hours + 1):
        forecast_ts = latest_timestamp + pd.Timedelta(hours=step)
        hour = forecast_ts.hour
        price_anchor = projected_prices[-24] if len(projected_prices) >= 24 else projected_prices[0]
        recent_window = projected_prices[-24:] if len(projected_prices) >= 24 else projected_prices
        rolling_mean = float(np.mean(recent_window))
        rolling_std = float(max(np.std(recent_window), 4.0))

        demand_anchor = _hourly_regime_anchor(feature_frame, "demand_mw", hour, int(forecast_ts.day_of_week), float(latest["demand_mw"]))
        wind_anchor = _hourly_regime_anchor(
            feature_frame,
            "wind_generation_estimate",
            hour,
            int(forecast_ts.day_of_week),
            float(latest["wind_generation_estimate"]),
        )
        solar_anchor = _hourly_regime_anchor(
            feature_frame,
            "solar_generation_estimate",
            hour,
            int(forecast_ts.day_of_week),
            float(latest["solar_generation_estimate"]),
        )
        temp_anchor = _hourly_regime_anchor(feature_frame, "temperature_c", hour, int(forecast_ts.day_of_week), float(latest["temperature_c"]))
        wind_speed_anchor = _hourly_anchor(feature_frame, "wind_speed", hour, float(latest["wind_speed"]))
        precip_anchor = _hourly_anchor(feature_frame, "precipitation", hour, float(latest["precipitation"]))
        decay = max(0.18, 1.0 - (step / 30.0))
        event_decay = max(0.25, 1.0 - (step / 20.0))
        overnight_softening = -120.0 if hour < 6 else 0.0
        peak_tightening = 280.0 if 17 <= hour <= 21 else 0.0
        demand_signal = demand_anchor + (demand_deviation * decay) + peak_tightening + overnight_softening + (
            float(latest["event_impact"]) * 80.0 * event_decay
        )
        wind_signal = wind_anchor + (wind_deviation * decay * 0.85)
        solar_signal = max(0.0, solar_anchor + (solar_deviation * decay * 0.75))
        temp_signal = temp_anchor + (temp_deviation * decay * 0.7)

        row = latest.copy()
        row["timestamp"] = forecast_ts
        row["hour"] = hour
        row["day_of_week"] = forecast_ts.day_of_week
        row["forecast_step"] = step
        row["temperature_c"] = max(-8.0, temp_signal)
        row["wind_speed"] = max(1.5, wind_speed_anchor + ((wind_signal - wind_anchor) / 600.0))
        row["wind_generation_estimate"] = max(500.0, wind_signal)
        row["solar_generation_estimate"] = solar_signal
        row["precipitation"] = max(0.0, precip_anchor)
        row["demand_mw"] = max(12000.0, demand_signal)
        row["demand_change"] = row["demand_mw"] - float(latest["demand_mw"])
        row["price_lag_1"] = rolling_price
        row["price_lag_24"] = price_anchor
        row["rolling_mean_24"] = rolling_mean
        row["rolling_std_24"] = rolling_std
        row["event_count"] = float(latest["event_count"])
        row["event_severity"] = float(latest["event_severity"])
        row["event_impact"] = float(latest["event_impact"])
        row["wind_to_demand_ratio"] = row["wind_generation_estimate"] / row["demand_mw"]
        row["solar_to_demand_ratio"] = row["solar_generation_estimate"] / row["demand_mw"]
        row["net_load_mw"] = row["demand_mw"] - row["wind_generation_estimate"] - row["solar_generation_estimate"]
        row["net_load_change"] = row["net_load_mw"] - float(latest["net_load_mw"])
        row["renewable_share"] = (
            (row["wind_generation_estimate"] + row["solar_generation_estimate"]) / row["demand_mw"]
        )
        row["scarcity_index"] = max(row["net_load_mw"] / row["demand_mw"], 0.0)

        row_frame = pd.DataFrame([row])
        dist = model.predict_distribution(row_frame).iloc[0]
        hourly_price_anchor = float(market_signature["hourly_price"].get(hour, market_signature["mean_price"]))
        dow_price_anchor = float(market_signature["dow_price"].get(int(forecast_ts.day_of_week), market_signature["mean_price"]))
        demand_reference = float(market_signature["hourly_demand"].get(hour, demand_anchor))
        wind_reference = float(market_signature["hourly_wind"].get(hour, wind_anchor))
        solar_reference = float(market_signature["hourly_solar"].get(hour, solar_anchor))
        temp_reference = float(market_signature["hourly_temp"].get(hour, temp_anchor))
        structural_target = (
            (0.72 * hourly_price_anchor)
            + (0.28 * dow_price_anchor)
            + (float(market_signature["demand_beta"]) * ((row["demand_mw"] - demand_reference) / 1000.0))
            + (float(market_signature["wind_beta"]) * ((row["wind_generation_estimate"] - wind_reference) / 1000.0))
            + (float(market_signature["solar_beta"]) * ((row["solar_generation_estimate"] - solar_reference) / 1000.0))
            + (float(market_signature["temp_beta"]) * (row["temperature_c"] - temp_reference))
            + (float(market_signature["event_beta"]) * row["event_impact"] * event_decay)
            + ((row["scarcity_index"] - float(market_signature["mean_scarcity"])) * 18.0)
        )
        blend = min(0.52, 0.2 + (step / 60.0))
        point_estimate = ((1.0 - blend) * float(dist["point_estimate"])) + (blend * structural_target)
        confidence_scale = 1.0 + abs(point_estimate - float(dist["point_estimate"])) / max(rolling_std, 6.0) * 0.12
        sigma_price = float(dist["sigma_price"]) * confidence_scale
        band_width = _Z95 * sigma_price
        lower_bound = point_estimate - band_width
        upper_bound = point_estimate + band_width
        rolling_price = point_estimate
        projected_prices.append(point_estimate)
        future_rows.append(row)
        spike_probability = min(
            0.95,
            max(
                0.05,
                ((point_estimate - float(row["rolling_mean_24"])) / max(float(row["rolling_std_24"]), 8.0)) * 0.12 + 0.18,
            ),
        )
        snapshot = {key: round(float(row[key]), 4) for key in FEATURE_COLUMNS if key in row}
        snapshot["sigma_price"] = round(sigma_price, 4)
        forecast = Forecast(
            market_id=market.id,
            forecast_for_timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime(),
            point_estimate=round(point_estimate, 2),
            lower_bound=round(float(lower_bound), 2),
            upper_bound=round(float(upper_bound), 2),
            currency=market_currency(market.code),
            spike_probability=round(float(spike_probability), 3),
            model_version=model.model_name,
            rationale_summary=model.explain(row),
            feature_snapshot_json=snapshot,
        )
        db.add(forecast)
        forecasts.append(forecast)

    db.commit()
    for forecast in forecasts:
        db.refresh(forecast)
    _cache_set(market.code, forecasts, metrics)
    return forecasts, metrics
