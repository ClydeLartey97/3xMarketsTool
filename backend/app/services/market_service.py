from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Forecast, Market, PricePoint


def list_markets(db: Session) -> list[Market]:
    return list(db.scalars(select(Market).order_by(Market.name)).all())


def get_market_by_id(db: Session, market_id: int) -> Market | None:
    return db.get(Market, market_id)


def get_market_by_code(db: Session, market_code: str) -> Market | None:
    return db.scalar(select(Market).where(Market.code == market_code))


@dataclass
class MarketOverviewEntry:
    """Lightweight per-market snapshot used by the home page grid.

    Replaces the previous client-side pattern where each card issued its
    own /prices and /forecast calls (plan §4 — Home Page Overview).
    """

    market: Market
    spot: float | None
    previous_spot: float | None
    change: float | None
    avg_price_24h: float | None
    next_forecast: Forecast | None
    spike_probability: float | None
    data_status: str


def _latest_prices(db: Session, market_id: int, limit: int = 25) -> list[PricePoint]:
    rows = db.scalars(
        select(PricePoint)
        .where(PricePoint.market_id == market_id)
        .order_by(PricePoint.timestamp.desc())
        .limit(limit)
    ).all()
    return list(reversed(list(rows)))


def _first_forecast(db: Session, market_id: int) -> Forecast | None:
    return db.scalar(
        select(Forecast)
        .where(Forecast.market_id == market_id)
        .order_by(Forecast.forecast_for_timestamp.asc())
        .limit(1)
    )


def build_markets_overview(db: Session) -> list[MarketOverviewEntry]:
    """Aggregate one row per market for the home grid in a single call."""
    out: list[MarketOverviewEntry] = []
    for market in list_markets(db):
        prices = _latest_prices(db, market.id)
        latest = prices[-1] if prices else None
        previous = prices[-2] if len(prices) >= 2 else None
        last_day = prices[-24:]
        avg_price_24h = (
            round(sum(p.price_value for p in last_day) / len(last_day), 4)
            if last_day
            else None
        )
        forecast = _first_forecast(db, market.id)
        change: float | None = None
        if latest is not None and previous is not None:
            change = round(float(latest.price_value) - float(previous.price_value), 4)

        out.append(
            MarketOverviewEntry(
                market=market,
                spot=float(latest.price_value) if latest else None,
                previous_spot=float(previous.price_value) if previous else None,
                change=change,
                avg_price_24h=avg_price_24h,
                next_forecast=forecast,
                spike_probability=float(forecast.spike_probability) if forecast else None,
                data_status=str((market.metadata_json or {}).get("data_status", "ready")),
            )
        )
    return out


def market_overview_to_dict(entry: MarketOverviewEntry) -> dict[str, Any]:
    """Render an overview entry as a JSON-ready dict for API responses."""
    forecast = entry.next_forecast
    forecast_payload: dict[str, Any] | None = None
    if forecast is not None:
        forecast_payload = {
            "forecast_for_timestamp": forecast.forecast_for_timestamp,
            "point_estimate": float(forecast.point_estimate),
            "lower_bound": float(forecast.lower_bound),
            "upper_bound": float(forecast.upper_bound),
            "currency": forecast.currency,
            "spike_probability": float(forecast.spike_probability),
        }
    market = entry.market
    return {
        "market": {
            "id": market.id,
            "name": market.name,
            "code": market.code,
            "commodity_type": market.commodity_type,
            "region": market.region,
            "timezone": market.timezone,
            "data_status": entry.data_status,
            "metadata": market.metadata_json or {},
        },
        "spot": entry.spot,
        "previous_spot": entry.previous_spot,
        "change": entry.change,
        "avg_price_24h": entry.avg_price_24h,
        "spike_probability": entry.spike_probability,
        "next_forecast": forecast_payload,
        "data_status": entry.data_status,
    }
