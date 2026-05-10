from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Market, PricePoint


_CACHE_TTL = timedelta(hours=6)
_correlation_cache: dict[int, tuple[datetime, dict[str, dict[str, float]]]] = {}


def invalidate_correlation_cache() -> None:
    _correlation_cache.clear()


def get_correlation_matrix(
    db: Session,
    *,
    lookback_hours: int = 24 * 365,
    force_refresh: bool = False,
) -> dict[str, dict[str, float]]:
    cache_key = int(lookback_hours)
    now = datetime.now(timezone.utc)
    cached = _correlation_cache.get(cache_key)
    if cached and not force_refresh:
        cached_at, matrix = cached
        if now - cached_at < _CACHE_TTL:
            return matrix

    markets = list(db.scalars(select(Market).order_by(Market.code.asc())).all())
    since = now - timedelta(hours=lookback_hours)
    returns_by_market: dict[str, pd.Series] = {}
    for market in markets:
        prices = list(
            db.scalars(
                select(PricePoint)
                .where(PricePoint.market_id == market.id, PricePoint.timestamp >= since)
                .order_by(PricePoint.timestamp.asc())
            ).all()
        )
        returns = _hourly_returns(prices)
        if not returns.empty:
            returns_by_market[market.code] = returns

    if not returns_by_market:
        return {}

    frame = pd.DataFrame(returns_by_market).dropna(how="all")
    corr = frame.corr(min_periods=24).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    for code in corr.columns:
        corr.loc[code, code] = 1.0

    matrix = {
        row_code: {
            col_code: round(float(np.clip(corr.loc[row_code, col_code], -1.0, 1.0)), 6)
            for col_code in corr.columns
        }
        for row_code in corr.index
    }
    _correlation_cache[cache_key] = (now, matrix)
    return matrix


def _hourly_returns(prices: list[PricePoint]) -> pd.Series:
    if len(prices) < 3:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(point.timestamp).tz_convert("UTC") if pd.Timestamp(point.timestamp).tzinfo else pd.Timestamp(point.timestamp).tz_localize("UTC") for point in prices],
            "price": [float(point.price_value) for point in prices],
        }
    )
    series = (
        frame.dropna()
        .assign(timestamp=lambda item: item["timestamp"].dt.floor("h"))
        .drop_duplicates("timestamp", keep="last")
        .set_index("timestamp")["price"]
        .sort_index()
    )
    previous = series.shift(1)
    reference = previous.abs().clip(lower=1.0)
    returns = (series - previous) / reference
    return returns.replace([np.inf, -np.inf], np.nan).dropna()
