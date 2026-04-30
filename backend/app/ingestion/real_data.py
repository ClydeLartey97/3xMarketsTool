"""Real data ingestion for 3x power market platform.

Priority per market:
  US markets  → EIA API v2 (demand + generation) + yfinance (NG=F gas price)
  GB market   → ELEXON BMRS API (Market Index Data — actual spot price)
  All markets → Open-Meteo (free weather, no auth needed)
  Fallback    → Calibrated synthetic if any API is unavailable
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Market metadata ────────────────────────────────────────────────────────────

EIA_RESPONDENTS: dict[str, str] = {
    "ERCOT_NORTH": "ERCO",
    "ERCOT_HOUSTON": "ERCO",
    "PJM_WESTERN_HUB": "PJM",
    "NYISO_ZONE_J": "NYIS",
    "ISONE_MASS_HUB": "ISNE",
}

MARKET_COORDS: dict[str, tuple[float, float]] = {
    "ERCOT_NORTH": (32.7767, -96.7970),
    "ERCOT_HOUSTON": (29.7604, -95.3698),
    "PJM_WESTERN_HUB": (40.4406, -79.9959),
    "NYISO_ZONE_J": (40.7128, -74.0060),
    "ISONE_MASS_HUB": (42.3601, -71.0589),
    "GB_POWER": (51.5074, -0.1278),
    "EPEX_DE": (50.1109, 8.6821),
    "EPEX_FR": (48.8566, 2.3522),
    "NORDPOOL_SE3": (59.3293, 18.0686),
}

# Approximate regional peak demand (MW) for price model normalisation
MARKET_PEAK_DEMAND: dict[str, float] = {
    "ERCOT_NORTH": 47000,
    "ERCOT_HOUSTON": 31000,
    "PJM_WESTERN_HUB": 160000,
    "NYISO_ZONE_J": 35000,
    "ISONE_MASS_HUB": 28000,
    "GB_POWER": 55000,
    "EPEX_DE": 90000,
    "EPEX_FR": 100000,
    "NORDPOOL_SE3": 25000,
}

MARKET_REGIONAL_BASIS: dict[str, float] = {
    "ERCOT_NORTH": 0.0,
    "ERCOT_HOUSTON": 3.0,
    "PJM_WESTERN_HUB": 7.0,
    "NYISO_ZONE_J": 18.0,   # NYC congestion premium
    "ISONE_MASS_HUB": 12.0,
    "GB_POWER": 0.0,         # ELEXON gives direct price
    "EPEX_DE": 0.0,
    "EPEX_FR": 4.0,
    "NORDPOOL_SE3": -8.0,    # Hydro premium for Nordics
}

MARKET_WIND_INSTALLED: dict[str, float] = {
    "ERCOT_NORTH": 18000,
    "ERCOT_HOUSTON": 5000,
    "PJM_WESTERN_HUB": 12000,
    "NYISO_ZONE_J": 3000,
    "ISONE_MASS_HUB": 6000,
    "GB_POWER": 30000,
    "EPEX_DE": 65000,
    "EPEX_FR": 24000,
    "NORDPOOL_SE3": 18000,
}

MARKET_SOLAR_INSTALLED: dict[str, float] = {
    "ERCOT_NORTH": 12000,
    "ERCOT_HOUSTON": 8000,
    "PJM_WESTERN_HUB": 8000,
    "NYISO_ZONE_J": 2000,
    "ISONE_MASS_HUB": 4000,
    "GB_POWER": 14000,
    "EPEX_DE": 80000,
    "EPEX_FR": 22000,
    "NORDPOOL_SE3": 4000,
}

EUROPEAN_MARKETS = {"EPEX_DE", "EPEX_FR", "NORDPOOL_SE3"}
GB_MARKETS = {"GB_POWER"}

# Currency that the stored `price_value` is denominated in, per market.
# Phase-2 fix: previously GB prices were silently converted GBP→USD on
# ingestion, leaving the DB with mixed undocumented currencies. Each market
# now stores its native currency and the risk engine handles FX explicitly.
MARKET_CURRENCY: dict[str, str] = {
    "ERCOT_NORTH": "USD",
    "ERCOT_HOUSTON": "USD",
    "PJM_WESTERN_HUB": "USD",
    "NYISO_ZONE_J": "USD",
    "ISONE_MASS_HUB": "USD",
    "GB_POWER": "GBP",
    "EPEX_DE": "EUR",
    "EPEX_FR": "EUR",
    "NORDPOOL_SE3": "EUR",
}


def market_currency(market_code: str) -> str:
    return MARKET_CURRENCY.get(market_code, "USD")

EIA_BASE = "https://api.eia.gov/v2"
OPENMETEO_BASE = "https://api.open-meteo.com/v1"
OPENMETEO_ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1"
ELEXON_BASE = "https://data.elexon.co.uk/bmrs/api/v1"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return _ensure_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_time_windows(start: datetime, end: datetime, window_days: int):
    cursor = _ensure_utc(start)
    limit = _ensure_utc(end)
    step = timedelta(days=window_days)
    while cursor < limit:
        next_cursor = min(cursor + step, limit)
        yield cursor, next_cursor
        cursor = next_cursor


def _iter_month_windows(start: datetime, end: datetime):
    cursor = _ensure_utc(start)
    limit = _ensure_utc(end)
    while cursor < limit:
        if cursor.month == 12:
            next_month = datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month = datetime(cursor.year, cursor.month + 1, 1, tzinfo=timezone.utc)
        next_cursor = min(next_month, limit)
        yield cursor, next_cursor
        cursor = next_cursor


# ── Weather (Open-Meteo, free, no auth) ───────────────────────────────────────

def fetch_weather(lat: float, lon: float, past_days: int = 14) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,windspeed_10m,direct_radiation,precipitation",
        "past_days": past_days,
        "forecast_days": 7,
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{OPENMETEO_BASE}/forecast", params=params)
            resp.raise_for_status()
            data = resp.json()
        h = data["hourly"]
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(h["time"], utc=True),
            "temperature_c": h["temperature_2m"],
            "wind_speed": h["windspeed_10m"],
            "direct_radiation": h.get("direct_radiation", [0.0] * len(h["time"])),
            "precipitation": h.get("precipitation", [0.0] * len(h["time"])),
        })
        logger.info("Open-Meteo: fetched %d weather points (%.2f, %.2f)", len(df), lat, lon)
        return df
    except Exception as exc:
        logger.warning("Open-Meteo fetch failed (%.2f, %.2f): %s", lat, lon, exc)
        return pd.DataFrame()


def fetch_weather_archive(lat: float, lon: float, start: datetime, end: datetime) -> pd.DataFrame:
    """Fetch historical hourly weather from Open-Meteo's archive API."""
    start_utc = _ensure_utc(start)
    end_utc = _ensure_utc(end)
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,wind_speed_10m,direct_radiation,precipitation",
        "start_date": start_utc.date().isoformat(),
        "end_date": end_utc.date().isoformat(),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    try:
        with httpx.Client(timeout=35.0) as client:
            resp = client.get(f"{OPENMETEO_ARCHIVE_BASE}/archive", params=params)
            resp.raise_for_status()
            data = resp.json()
        h = data["hourly"]
        wind_values = h.get("wind_speed_10m", h.get("windspeed_10m", [0.0] * len(h["time"])))
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(h["time"], utc=True),
            "temperature_c": h["temperature_2m"],
            "wind_speed": wind_values,
            "direct_radiation": h.get("direct_radiation", [0.0] * len(h["time"])),
            "precipitation": h.get("precipitation", [0.0] * len(h["time"])),
        })
        df = df[(df["timestamp"] >= start_utc) & (df["timestamp"] <= end_utc)]
        df = df.sort_values("timestamp").reset_index(drop=True)
        logger.info(
            "Open-Meteo archive: fetched %d weather points (%.2f, %.2f)",
            len(df),
            lat,
            lon,
        )
        return df
    except Exception as exc:
        logger.warning("Open-Meteo archive fetch failed (%.2f, %.2f): %s", lat, lon, exc)
        return pd.DataFrame()


# ── EIA (US electricity grid data) ────────────────────────────────────────────

def fetch_eia_demand(respondent: str, api_key: str, days: int = 14) -> pd.DataFrame:
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][0]": respondent,
        "facets[type][0]": "D",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": days * 24 + 24,
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{EIA_BASE}/electricity/rto/region-data/data/", params=params)
            resp.raise_for_status()
            records = resp.json()["response"]["data"]
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
        df["demand_mw"] = pd.to_numeric(df["value"], errors="coerce")
        result = df[["timestamp", "demand_mw"]].dropna().sort_values("timestamp").reset_index(drop=True)
        logger.info("EIA demand (%s): fetched %d hourly points", respondent, len(result))
        return result
    except Exception as exc:
        logger.warning("EIA demand fetch failed (%s): %s", respondent, exc)
        return pd.DataFrame()


def fetch_eia_generation(respondent: str, fuel_type: str, api_key: str, days: int = 14) -> pd.DataFrame:
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][0]": respondent,
        "facets[fueltype][0]": fuel_type,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": days * 24 + 24,
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{EIA_BASE}/electricity/rto/fuel-type-data/data/", params=params)
            resp.raise_for_status()
            records = resp.json()["response"]["data"]
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        result = df[["timestamp", "value"]].dropna().sort_values("timestamp").reset_index(drop=True)
        logger.info("EIA gen (%s/%s): fetched %d points", respondent, fuel_type, len(result))
        return result
    except Exception as exc:
        logger.warning("EIA gen fetch failed (%s/%s): %s", respondent, fuel_type, exc)
        return pd.DataFrame()


def _fetch_eia_records(endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    page_size = 5000
    try:
        with httpx.Client(timeout=35.0) as client:
            while True:
                page_params = {**params, "length": page_size, "offset": offset}
                resp = client.get(f"{EIA_BASE}/{endpoint}", params=page_params)
                resp.raise_for_status()
                page = resp.json().get("response", {}).get("data", [])
                if not page:
                    break
                records.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size
    except Exception as exc:
        logger.warning("EIA paged fetch failed (%s): %s", endpoint, exc)
        return []
    return records


def _eia_hourly_frame(records: list[dict[str, Any]], value_column: str) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
    df[value_column] = pd.to_numeric(df["value"], errors="coerce")
    return (
        df[["timestamp", value_column]]
        .dropna()
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def fetch_eia_demand_window(
    respondent: str,
    api_key: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][0]": respondent,
        "facets[type][0]": "D",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "start": _ensure_utc(start).strftime("%Y-%m-%dT%H"),
        "end": _ensure_utc(end).strftime("%Y-%m-%dT%H"),
    }
    records = _fetch_eia_records("electricity/rto/region-data/data/", params)
    return _eia_hourly_frame(records, "demand_mw")


def fetch_eia_generation_window(
    respondent: str,
    fuel_type: str,
    api_key: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][0]": respondent,
        "facets[fueltype][0]": fuel_type,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "start": _ensure_utc(start).strftime("%Y-%m-%dT%H"),
        "end": _ensure_utc(end).strftime("%Y-%m-%dT%H"),
    }
    records = _fetch_eia_records("electricity/rto/fuel-type-data/data/", params)
    return _eia_hourly_frame(records, "value")


def fetch_eia_demand_history(respondent: str, api_key: str, start: datetime, end: datetime) -> pd.DataFrame:
    frames = [fetch_eia_demand_window(respondent, api_key, w_start, w_end) for w_start, w_end in _iter_month_windows(start, end)]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    return result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def fetch_eia_generation_history(
    respondent: str,
    fuel_type: str,
    api_key: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    frames = [
        fetch_eia_generation_window(respondent, fuel_type, api_key, w_start, w_end)
        for w_start, w_end in _iter_month_windows(start, end)
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    return result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


# ── ELEXON (GB actual spot price) ─────────────────────────────────────────────

def _parse_elexon_mid_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "startTime" in df.columns:
        df["timestamp"] = pd.to_datetime(df["startTime"], utc=True, errors="coerce")
    else:
        df["settlement_dt"] = pd.to_datetime(df["settlementDate"])
        df["timestamp"] = df["settlement_dt"] + pd.to_timedelta(
            (df["settlementPeriod"].astype(int) - 1) * 30,
            unit="m",
        )
        df["timestamp"] = df["timestamp"].dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT")
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
    df["price_gbp_mwh"] = pd.to_numeric(df["price"], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    else:
        df["volume"] = 0.0
    df = df.dropna(subset=["timestamp", "price_gbp_mwh"])
    if df.empty:
        return pd.DataFrame()

    df["weighted_price"] = df["price_gbp_mwh"] * df["volume"]
    grouped = (
        df.groupby("timestamp", as_index=False)
        .agg(
            volume_sum=("volume", "sum"),
            weighted_sum=("weighted_price", "sum"),
            mean_price=("price_gbp_mwh", "mean"),
        )
    )
    grouped["price_gbp_mwh"] = np.where(
        grouped["volume_sum"] > 0,
        grouped["weighted_sum"] / grouped["volume_sum"],
        grouped["mean_price"],
    )
    result = (
        grouped[["timestamp", "price_gbp_mwh"]]
        .set_index("timestamp")
        .sort_index()
        .resample("1h")
        .mean()
        .dropna()
        .reset_index()
    )
    return result.sort_values("timestamp").reset_index(drop=True)


def _fetch_elexon_prices_window(start: datetime, end: datetime) -> pd.DataFrame:
    """Fetch a single short ELEXON MID window."""
    params = {"from": _iso_z(start), "to": _iso_z(end)}
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{ELEXON_BASE}/datasets/MID", params=params)
            resp.raise_for_status()
            records = resp.json().get("data", [])
        return _parse_elexon_mid_records(records)
    except Exception as exc:
        logger.warning("ELEXON fetch failed (%s → %s): %s", _iso_z(start), _iso_z(end), exc)
        return pd.DataFrame()


def fetch_elexon_prices_between(start: datetime, end: datetime, window_days: int = 7) -> pd.DataFrame:
    """Fetch UK Market Index Data from ELEXON BMRS in API-safe windows."""
    frames = [_fetch_elexon_prices_window(w_start, w_end) for w_start, w_end in _iter_time_windows(start, end, window_days)]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    logger.info("ELEXON: fetched %d hourly price points", len(df))
    return df


def fetch_elexon_prices(days: int = 14) -> pd.DataFrame:
    """Fetch UK Market Index Data from ELEXON BMRS (free, no auth)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return fetch_elexon_prices_between(start, end, window_days=7)


# ── Energy prices from yfinance ───────────────────────────────────────────────

def get_gas_price_usd_mmbtu() -> float:
    """Henry Hub natural gas spot price (US benchmark)."""
    try:
        import yfinance as yf
        hist = yf.Ticker("NG=F").history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            logger.info("yfinance NG=F: $%.3f/mmbtu", price)
            return price
    except Exception as exc:
        logger.warning("yfinance NG=F failed: %s", exc)
    return 2.85


def get_ttf_gas_price_eur_mwh() -> float:
    """TTF natural gas price for European markets (EUR/MWh)."""
    try:
        import yfinance as yf
        hist = yf.Ticker("TTF=F").history(period="5d")
        if not hist.empty:
            price_eur_mwh = float(hist["Close"].iloc[-1])
            logger.info("yfinance TTF=F: €%.2f/MWh", price_eur_mwh)
            return price_eur_mwh
    except Exception as exc:
        logger.warning("yfinance TTF=F failed: %s", exc)
    return 38.0  # EUR/MWh fallback


def get_gbp_usd_rate() -> float:
    """GBP/USD exchange rate."""
    try:
        import yfinance as yf
        hist = yf.Ticker("GBPUSD=X").history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 1.27


# ── Power price model (merit order / gas stack) ───────────────────────────────

def compute_power_price(
    gas_price: float,
    demand_mw: float,
    wind_mw: float,
    solar_mw: float,
    temp_c: float,
    demand_peak_mw: float,
    regional_basis: float,
    hour: int,
    rng: np.random.Generator,
    noise_scale: float = 3.5,
    is_european: bool = False,
    is_nordic: bool = False,
) -> float:
    """
    Gas-stack merit-order price model.

    For European/Nordic markets gas_price is in EUR/MWh directly.
    For US markets gas_price is in USD/mmbtu and converted via heat rate.
    """
    if is_european or is_nordic:
        # gas_price already in EUR/MWh; add variable O&M
        gas_var_cost = gas_price * 0.95 + 3.5
        if is_nordic:
            # Hydro-heavy grids price off marginal water value, lower baseline
            gas_var_cost = gas_price * 0.45 + 2.0
    else:
        # US: gas_price in USD/mmbtu, heat rate 7.5 mmbtu/MWh
        gas_var_cost = gas_price * 7.5 + 3.5

    demand_ratio = demand_mw / max(demand_peak_mw, 1.0)

    # ── Merit order dispatch stack ─────────────────────────────────────────
    if demand_ratio < 0.50:
        base = gas_var_cost * 0.42
        demand_premium = demand_ratio * 6.0
    elif demand_ratio < 0.68:
        base = gas_var_cost * 0.68
        demand_premium = (demand_ratio - 0.50) * 28.0
    elif demand_ratio < 0.80:
        base = gas_var_cost * 0.88
        demand_premium = (demand_ratio - 0.68) * 52.0
    elif demand_ratio < 0.89:
        base = gas_var_cost * 1.05
        demand_premium = (demand_ratio - 0.80) * 110.0
    elif demand_ratio < 0.95:
        base = gas_var_cost * 1.22
        demand_premium = (demand_ratio - 0.89) * 260.0
    else:
        # Scarcity — only expensive peakers left
        base = gas_var_cost * 1.45
        demand_premium = (demand_ratio - 0.95) ** 1.55 * 1400.0

    # ── Renewable suppression ──────────────────────────────────────────────
    renewable_frac = (wind_mw + solar_mw) / max(demand_mw, 1.0)
    renewable_discount = min(renewable_frac * 32.0, 30.0)

    # Negative price regime (excess renewables)
    if renewable_frac > 0.88 and demand_ratio < 0.52:
        return round(float(rng.normal(-18.0, 9.0)), 2)

    # ── Temperature premium ────────────────────────────────────────────────
    if temp_c > 35.0:
        temp_effect = (temp_c - 35.0) * 5.5
    elif temp_c > 30.0:
        temp_effect = (temp_c - 30.0) * 2.2
    elif temp_c < 0.0:
        temp_effect = abs(temp_c) * 3.8
    elif temp_c < 8.0:
        temp_effect = (8.0 - temp_c) * 1.4
    else:
        temp_effect = 0.0

    # ── Intraday shaping ───────────────────────────────────────────────────
    hour_shapes = {
        0: -3.5, 1: -4.5, 2: -5.5, 3: -6.0, 4: -5.0, 5: -3.0,
        6: 1.5,  7: 5.5,  8: 7.5,  9: 6.0,  10: 4.5, 11: 3.0,
        12: 3.0, 13: 3.5, 14: 4.5, 15: 6.0, 16: 9.0, 17: 13.0,
        18: 15.0, 19: 13.0, 20: 10.0, 21: 7.0, 22: 4.5, 23: 1.5,
    }
    hour_effect = hour_shapes.get(hour, 0.0)

    price = base + demand_premium - renewable_discount + temp_effect + hour_effect + regional_basis
    price += float(rng.normal(0.0, noise_scale))
    return round(max(-100.0, price), 2)


# ── Generation estimates from weather ─────────────────────────────────────────

def _wind_gen(wind_speed_ms: float, installed_mw: float) -> float:
    if wind_speed_ms < 2.5:
        return 0.0
    if wind_speed_ms > 25.0:
        return 0.0
    cf = min(((wind_speed_ms - 2.5) / 10.0) ** 3 * 0.92, 0.92) if wind_speed_ms < 12.5 else 0.92
    return round(cf * installed_mw, 0)


def _solar_gen(radiation_wm2: float, installed_mw: float, hour: int) -> float:
    if hour < 5 or hour > 21 or radiation_wm2 <= 0:
        return 0.0
    cf = min(radiation_wm2 / 950.0, 1.0) * 0.82
    return round(cf * installed_mw, 0)


# ── Synthetic demand (when EIA unavailable) ───────────────────────────────────

_HOUR_SHAPE = {
    0: 0.75, 1: 0.72, 2: 0.70, 3: 0.69, 4: 0.71, 5: 0.76,
    6: 0.83, 7: 0.91, 8: 0.97, 9: 0.99, 10: 1.00, 11: 1.01,
    12: 1.00, 13: 1.00, 14: 1.01, 15: 1.02, 16: 1.04, 17: 1.09,
    18: 1.11, 19: 1.09, 20: 1.05, 21: 0.99, 22: 0.91, 23: 0.83,
}

_MONTH_FACTOR = {
    1: 0.95, 2: 0.94, 3: 0.90, 4: 0.86, 5: 0.88, 6: 0.96,
    7: 1.04, 8: 1.05, 9: 0.92, 10: 0.88, 11: 0.92, 12: 0.97,
}


def synthetic_demand(
    hour: int,
    dow: int,
    temp_c: float,
    demand_baseline: float,
    month: int,
    rng: np.random.Generator,
) -> float:
    wd = 0.87 if dow >= 5 else 1.02
    cooling = max(0.0, (temp_c - 30.0) * 0.020 * demand_baseline)
    heating = max(0.0, (5.0 - temp_c) * 0.015 * demand_baseline)
    base = (demand_baseline * _HOUR_SHAPE.get(hour, 0.90) * wd
            * _MONTH_FACTOR.get(month, 0.95) + cooling + heating)
    noise = float(rng.normal(0.0, demand_baseline * 0.015))
    return max(demand_baseline * 0.38, base + noise)


def _synthetic_weather_df(
    timestamps: list[datetime],
    market_code: str,
    rng: np.random.Generator,
) -> pd.DataFrame:
    coords = MARKET_COORDS.get(market_code, (35.0, -90.0))
    lat = coords[0]
    month = datetime.now(timezone.utc).month
    # Rough base temp from latitude
    temp_base = {
        1: -5 + lat * 0.65, 2: -3 + lat * 0.65, 3: 5 + lat * 0.48,
        4: 12 + lat * 0.28, 5: 18 + lat * 0.18, 6: 24 + lat * 0.14,
        7: 27 + lat * 0.12, 8: 26 + lat * 0.13, 9: 20 + lat * 0.20,
        10: 13 + lat * 0.28, 11: 5 + lat * 0.48, 12: -2 + lat * 0.62,
    }.get(month, 15.0)
    rows = []
    for ts in timestamps:
        diurnal = 4.0 * float(np.sin((ts.hour - 14) * np.pi / 12.0))
        temp = temp_base + diurnal + float(rng.normal(0.0, 2.2))
        wind = max(0.5, float(rng.lognormal(1.2, 0.4)))
        radiation = (
            max(0.0, 620.0 * float(np.sin((ts.hour - 6) * np.pi / 12.0))
                * float(rng.uniform(0.28, 1.0)))
            if 6 <= ts.hour <= 20 else 0.0
        )
        rows.append({
            "timestamp": ts,
            "temperature_c": round(temp, 1),
            "wind_speed": round(wind, 1),
            "direct_radiation": round(radiation, 0),
            "precipitation": max(0.0, float(rng.exponential(0.18))),
        })
    return pd.DataFrame(rows)


def _timestamp_key(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.floor("h").to_pydatetime().replace(tzinfo=None)


def _set_market_data_status(market: Any, status: str) -> None:
    metadata = dict(market.metadata_json or {})
    if metadata.get("data_status") != status:
        metadata["data_status"] = status
        market.metadata_json = metadata


def _has_real_price_source(sources: dict[str, str]) -> bool:
    return sources.get("prices") in {"elexon-bmrs"}


def _apply_data_status(market: Any, sources: dict[str, str], *, demo_mode: bool) -> str:
    status = "ready" if demo_mode or _has_real_price_source(sources) else "degraded"
    _set_market_data_status(market, status)
    return status


def _hourly_timestamps(start: datetime, end: datetime) -> list[datetime]:
    cursor = _ensure_utc(start).replace(minute=0, second=0, microsecond=0)
    limit = _ensure_utc(end)
    timestamps: list[datetime] = []
    while cursor < limit:
        timestamps.append(cursor)
        cursor += timedelta(hours=1)
    return timestamps


def _normalise_hourly(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    frame = df.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.floor("h")
    keep = ["timestamp", *columns]
    return (
        frame[keep]
        .dropna(subset=["timestamp"])
        .groupby("timestamp", as_index=False)
        .mean(numeric_only=True)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def _insert_market_frames(
    db: Any,
    market: Any,
    market_code: str,
    *,
    weather_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    wind_eia_df: pd.DataFrame,
    solar_eia_df: pd.DataFrame,
    gb_prices_df: pd.DataFrame,
    gas_price: float,
    sources: dict[str, str],
    start: datetime,
    end: datetime,
    rng: np.random.Generator,
) -> int:
    from app.models import DemandPoint, PricePoint, WeatherPoint
    from sqlalchemy import select

    is_european = market_code in EUROPEAN_MARKETS
    is_nordic = market_code == "NORDPOOL_SE3"
    is_gb = market_code in GB_MARKETS

    if weather_df.empty:
        weather_df = _synthetic_weather_df(_hourly_timestamps(start, end), market_code, rng)
        sources["weather"] = "synthetic"
    else:
        weather_df = _normalise_hourly(
            weather_df,
            ["temperature_c", "wind_speed", "direct_radiation", "precipitation"],
        )

    for frame_name, frame in [
        ("demand", demand_df),
        ("wind", wind_eia_df),
        ("solar", solar_eia_df),
        ("gb_prices", gb_prices_df),
    ]:
        if frame.empty:
            continue
        if frame_name == "demand":
            demand_df = _normalise_hourly(frame, ["demand_mw"])
        elif frame_name == "wind":
            wind_eia_df = _normalise_hourly(frame, ["wind_mw"])
        elif frame_name == "solar":
            solar_eia_df = _normalise_hourly(frame, ["solar_mw"])
        else:
            gb_prices_df = _normalise_hourly(frame, ["price_gbp_mwh"])

    merged = weather_df.copy()
    for extra_df, col in [
        (demand_df, "demand_mw"),
        (wind_eia_df, "wind_mw"),
        (solar_eia_df, "solar_mw"),
    ]:
        if not extra_df.empty:
            merged = merged.merge(extra_df[["timestamp", col]], on="timestamp", how="left")
        else:
            merged[col] = np.nan

    if not gb_prices_df.empty:
        merged = merged.merge(gb_prices_df[["timestamp", "price_gbp_mwh"]], on="timestamp", how="left")
    else:
        merged["price_gbp_mwh"] = np.nan

    peak_demand = MARKET_PEAK_DEMAND.get(market_code, 50000.0)
    demand_baseline = peak_demand * 0.64
    wind_installed = MARKET_WIND_INSTALLED.get(market_code, 5000.0)
    solar_installed = MARKET_SOLAR_INSTALLED.get(market_code, 3000.0)
    regional_basis = MARKET_REGIONAL_BASIS.get(market_code, 0.0)

    for idx, row in merged.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        if pd.isna(row.get("demand_mw")):
            merged.at[idx, "demand_mw"] = synthetic_demand(
                ts.hour,
                ts.dayofweek,
                float(row["temperature_c"]),
                demand_baseline,
                ts.month,
                rng,
            )
        if pd.isna(row.get("wind_mw")):
            merged.at[idx, "wind_mw"] = _wind_gen(float(row["wind_speed"]), wind_installed)
        if pd.isna(row.get("solar_mw")):
            merged.at[idx, "solar_mw"] = _solar_gen(
                float(row.get("direct_radiation", 0.0)),
                solar_installed,
                ts.hour,
            )

    existing_ts = set(
        _timestamp_key(r[0]) for r in db.execute(
            select(PricePoint.timestamp).where(PricePoint.market_id == market.id)
        ).all()
    )

    inserted = 0
    for _, row in merged.iterrows():
        ts = pd.Timestamp(row["timestamp"]).to_pydatetime()
        ts_key = _timestamp_key(ts)
        if ts_key in existing_ts:
            continue

        demand_mw = float(row["demand_mw"])
        wind_mw = float(row.get("wind_mw", 0.0))
        solar_mw = float(row.get("solar_mw", 0.0))
        temp_c = float(row["temperature_c"])
        wind_speed = float(row["wind_speed"])
        precip = float(row.get("precipitation", 0.0))
        hour = pd.Timestamp(ts).hour

        if is_gb and not pd.isna(row.get("price_gbp_mwh")):
            price = float(row["price_gbp_mwh"])
            price_source = "elexon-bmrs"
        else:
            price = compute_power_price(
                gas_price=gas_price,
                demand_mw=demand_mw,
                wind_mw=wind_mw,
                solar_mw=solar_mw,
                temp_c=temp_c,
                demand_peak_mw=peak_demand,
                regional_basis=regional_basis,
                hour=hour,
                rng=rng,
                is_european=is_european,
                is_nordic=is_nordic,
            )
            price_source = "computed-fundamentals"
            sources.setdefault("prices", price_source)

        db.add(PricePoint(
            market_id=market.id,
            timestamp=ts,
            horizon_type="spot",
            price_value=price,
            currency=market_currency(market_code),
            source=price_source,
        ))
        db.add(WeatherPoint(
            market_id=market.id,
            timestamp=ts,
            temperature_c=temp_c,
            wind_speed=wind_speed,
            wind_generation_estimate=wind_mw,
            solar_generation_estimate=solar_mw,
            precipitation=precip,
            source=sources.get("weather", "synthetic"),
        ))
        db.add(DemandPoint(
            market_id=market.id,
            timestamp=ts,
            demand_mw=demand_mw,
            source=sources.get("demand", "computed"),
        ))
        existing_ts.add(ts_key)
        inserted += 1

    db.flush()
    return inserted


# ── Main ingestion orchestrator ───────────────────────────────────────────────

def populate_market_real_data(
    db: Any,
    market: Any,
    market_code: str,
    eia_api_key: str,
    days: int = 14,
) -> dict[str, str]:
    """
    Fetch and insert real data for one market.
    Returns a dict of {layer: source_description}.
    """
    rng = np.random.default_rng()
    sources: dict[str, str] = {}
    from app.core.config import get_settings

    settings = get_settings()

    is_european = market_code in EUROPEAN_MARKETS
    is_gb = market_code in GB_MARKETS
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    # ── Weather ───────────────────────────────────────────────────────────
    coords = MARKET_COORDS.get(market_code)
    weather_df = pd.DataFrame()
    if coords:
        weather_df = fetch_weather(coords[0], coords[1], past_days=days)
    if not weather_df.empty:
        sources["weather"] = "open-meteo"

    # ── Gas price ─────────────────────────────────────────────────────────
    if is_european or is_gb:
        gas_price = get_ttf_gas_price_eur_mwh()
        sources["gas_price"] = "yfinance-TTF"
    else:
        gas_price = get_gas_price_usd_mmbtu()
        sources["gas_price"] = "yfinance-NGAS"

    # ── US demand + generation (EIA) ──────────────────────────────────────
    respondent = EIA_RESPONDENTS.get(market_code)
    demand_df = pd.DataFrame()
    wind_eia_df = pd.DataFrame()
    solar_eia_df = pd.DataFrame()

    if respondent and eia_api_key:
        demand_df = fetch_eia_demand(respondent, eia_api_key, days=days)
        if not demand_df.empty:
            sources["demand"] = f"eia-{respondent}"
        raw_wind = fetch_eia_generation(respondent, "WND", eia_api_key, days=days)
        if not raw_wind.empty:
            wind_eia_df = raw_wind.rename(columns={"value": "wind_mw"})
        raw_solar = fetch_eia_generation(respondent, "SUN", eia_api_key, days=days)
        if not raw_solar.empty:
            solar_eia_df = raw_solar.rename(columns={"value": "solar_mw"})

    # ── GB actual spot price (ELEXON) ─────────────────────────────────────
    gb_prices_df = pd.DataFrame()
    if is_gb:
        gb_prices_df = fetch_elexon_prices(days=days)
        if not gb_prices_df.empty:
            sources["prices"] = "elexon-bmrs"

    inserted = _insert_market_frames(
        db,
        market,
        market_code,
        weather_df=weather_df,
        demand_df=demand_df,
        wind_eia_df=wind_eia_df,
        solar_eia_df=solar_eia_df,
        gb_prices_df=gb_prices_df,
        gas_price=gas_price,
        sources=sources,
        start=start,
        end=end,
        rng=rng,
    )
    _apply_data_status(market, sources, demo_mode=settings.demo_mode)
    logger.info(
        "Market %s: inserted %d new data points. Sources: %s",
        market_code, inserted, sources,
    )
    return sources


def backfill_market(
    market_code: str,
    lookback_days: int = 730,
    *,
    db: Any | None = None,
    eia_api_key: str | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Backfill one market with historical hourly data.

    Safe to re-run: insertion goes through the same hourly timestamp dedupe
    used by the regular refresh path.
    """
    if db is None:
        from app.core.config import get_settings
        from app.db.session import SessionLocal

        settings = get_settings()
        with SessionLocal() as session:
            summary = backfill_market(
                market_code,
                lookback_days=lookback_days,
                db=session,
                eia_api_key=eia_api_key if eia_api_key is not None else settings.eia_api_key,
                end=end,
            )
            session.commit()
            return summary

    from app.core.config import get_settings
    from app.models import Market, PricePoint
    from sqlalchemy import func, select

    settings = get_settings()
    api_key = eia_api_key if eia_api_key is not None else settings.eia_api_key
    market = db.scalar(select(Market).where(Market.code == market_code))
    if market is None:
        raise ValueError(f"Market not found: {market_code}")

    rng = np.random.default_rng()
    end_utc = _ensure_utc(end or datetime.now(timezone.utc))
    start_utc = end_utc - timedelta(days=lookback_days)
    sources: dict[str, str] = {}

    coords = MARKET_COORDS.get(market_code)
    weather_df = pd.DataFrame()
    if coords:
        weather_df = fetch_weather_archive(coords[0], coords[1], start_utc, end_utc)
    if not weather_df.empty:
        sources["weather"] = "open-meteo-archive"

    is_european = market_code in EUROPEAN_MARKETS
    is_gb = market_code in GB_MARKETS
    if is_european or is_gb:
        gas_price = get_ttf_gas_price_eur_mwh()
        sources["gas_price"] = "yfinance-TTF"
    else:
        gas_price = get_gas_price_usd_mmbtu()
        sources["gas_price"] = "yfinance-NGAS"

    respondent = EIA_RESPONDENTS.get(market_code)
    demand_df = pd.DataFrame()
    wind_eia_df = pd.DataFrame()
    solar_eia_df = pd.DataFrame()
    if respondent and api_key:
        demand_df = fetch_eia_demand_history(respondent, api_key, start_utc, end_utc)
        if not demand_df.empty:
            sources["demand"] = f"eia-{respondent}"
        raw_wind = fetch_eia_generation_history(respondent, "WND", api_key, start_utc, end_utc)
        if not raw_wind.empty:
            wind_eia_df = raw_wind.rename(columns={"value": "wind_mw"})
        raw_solar = fetch_eia_generation_history(respondent, "SUN", api_key, start_utc, end_utc)
        if not raw_solar.empty:
            solar_eia_df = raw_solar.rename(columns={"value": "solar_mw"})

    gb_prices_df = pd.DataFrame()
    if is_gb:
        gb_prices_df = fetch_elexon_prices_between(start_utc, end_utc, window_days=7)
        if not gb_prices_df.empty:
            sources["prices"] = "elexon-bmrs"

    inserted = _insert_market_frames(
        db,
        market,
        market_code,
        weather_df=weather_df,
        demand_df=demand_df,
        wind_eia_df=wind_eia_df,
        solar_eia_df=solar_eia_df,
        gb_prices_df=gb_prices_df,
        gas_price=gas_price,
        sources=sources,
        start=start_utc,
        end=end_utc,
        rng=rng,
    )
    data_status = _apply_data_status(market, sources, demo_mode=settings.demo_mode)
    price_points_after = db.scalar(
        select(func.count()).select_from(PricePoint).where(PricePoint.market_id == market.id)
    ) or 0
    real_price_points_after = db.scalar(
        select(func.count()).select_from(PricePoint).where(
            PricePoint.market_id == market.id,
            PricePoint.source.notin_(["computed-fundamentals", "synthetic"]),
        )
    ) or 0
    summary = {
        "market": market_code,
        "lookback_days": lookback_days,
        "start": start_utc.isoformat(),
        "end": end_utc.isoformat(),
        "inserted": inserted,
        "price_points_after": int(price_points_after),
        "real_price_points_after": int(real_price_points_after),
        "data_status": data_status,
        "sources": sources,
    }
    logger.info("Backfill summary: %s", summary)
    return summary
