"""FX rate lookup with a 1-hour in-process cache and hard-coded fallbacks.

Used by the risk engine to convert simulated P&L from a market's native
currency to GBP. Falls back to a static rate if the network call fails;
every fallback is logged so the user can see which numbers were estimated.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Hard-coded fallback rates (target → GBP). Roughly 2026-Q2 levels.
_FALLBACKS: dict[str, float] = {
    "GBP": 1.0,
    "USD": 0.79,   # 1 USD ≈ 0.79 GBP
    "EUR": 0.85,   # 1 EUR ≈ 0.85 GBP
}

_CACHE_TTL = timedelta(hours=1)
_cache: dict[str, tuple[float, datetime]] = {}


def _cached(key: str) -> Optional[float]:
    entry = _cache.get(key)
    if entry and (datetime.now(timezone.utc) - entry[1]) < _CACHE_TTL:
        return entry[0]
    return None


def _store(key: str, value: float) -> None:
    _cache[key] = (value, datetime.now(timezone.utc))


def fx_to_gbp(currency: str) -> float:
    """Return the multiplier that converts 1 unit of `currency` into GBP."""
    code = (currency or "USD").upper()
    if code == "GBP":
        return 1.0

    cached = _cached(code)
    if cached is not None:
        return cached

    rate: Optional[float] = None
    try:
        import yfinance as yf  # local import — optional dep
        # yfinance ticker convention: "USDGBP=X" gives USD→GBP cross.
        ticker = f"{code}GBP=X"
        hist = yf.Ticker(ticker).history(period="2d", interval="1h")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001 — never let FX crash the app
        logger.warning("FX fetch failed for %s→GBP: %s. Using fallback.", code, exc)

    if rate is None or rate <= 0:
        rate = _FALLBACKS.get(code, 1.0)
        logger.warning("FX fallback used for %s→GBP: %.4f", code, rate)

    _store(code, rate)
    return rate


def invalidate_fx_cache() -> None:
    _cache.clear()
