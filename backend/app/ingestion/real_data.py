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

EIA_BASE = "https://api.eia.gov/v2"
OPENMETEO_BASE = "https://api.open-meteo.com/v1"
ELEXON_BASE = "https://data.elexon.co.uk/bmrs/api/v1"

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


# ── ELEXON (GB actual spot price) ─────────────────────────────────────────────

def fetch_elexon_prices(days: int = 14) -> pd.DataFrame:
    """Fetch UK Market Index Data from ELEXON BMRS (free, no auth)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{ELEXON_BASE}/datasets/MID", params=params)
            resp.raise_for_status()
            records = resp.json().get("data", [])
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["settlement_dt"] = pd.to_datetime(df["settlementDate"])
        df["timestamp"] = df["settlement_dt"] + pd.to_timedelta(
            (df["settlementPeriod"].astype(int) - 1) * 30, unit="m"
        )
        df["timestamp"] = df["timestamp"].dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT")
        df = df.dropna(subset=["timestamp"])
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
        df["price_gbp_mwh"] = pd.to_numeric(df["price"], errors="coerce")
        df = df[["timestamp", "price_gbp_mwh"]].dropna()
        df = df.set_index("timestamp").resample("1h").mean().reset_index().sort_values("timestamp")
        logger.info("ELEXON: fetched %d hourly price points", len(df))
        return df
    except Exception as exc:
        logger.warning("ELEXON fetch failed: %s", exc)
        return pd.DataFrame()


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
    from app.models import DemandPoint, PricePoint, WeatherPoint
    from sqlalchemy import select

    rng = np.random.default_rng()
    sources: dict[str, str] = {}

    is_european = market_code in EUROPEAN_MARKETS
    is_nordic = market_code == "NORDPOOL_SE3"
    is_gb = market_code in GB_MARKETS

    # ── Weather ───────────────────────────────────────────────────────────
    coords = MARKET_COORDS.get(market_code)
    weather_df = pd.DataFrame()
    if coords:
        weather_df = fetch_weather(coords[0], coords[1], past_days=days)
    if not weather_df.empty:
        sources["weather"] = "open-meteo"
    else:
        now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        timestamps = [now_utc - timedelta(hours=i) for i in range(days * 24, 0, -1)]
        weather_df = _synthetic_weather_df(timestamps, market_code, rng)
        sources["weather"] = "synthetic"

    weather_df["timestamp"] = pd.to_datetime(weather_df["timestamp"], utc=True).dt.floor("h")

    # ── Gas price ─────────────────────────────────────────────────────────
    if is_european or is_gb:
        gas_price = get_ttf_gas_price_eur_mwh()
        sources["gas_price"] = "yfinance-TTF"
    else:
        gas_price = get_gas_price_usd_mmbtu()
        sources["gas_price"] = "yfinance-NGAS"

    gbp_usd = get_gbp_usd_rate() if is_gb else 1.0

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

    # ── Merge all series on hourly UTC timestamps ─────────────────────────
    merged = weather_df.copy()
    for extra_df, col in [
        (demand_df, "demand_mw"),
        (wind_eia_df, "wind_mw"),
        (solar_eia_df, "solar_mw"),
    ]:
        if not extra_df.empty:
            extra_df = extra_df.copy()
            extra_df["timestamp"] = pd.to_datetime(extra_df["timestamp"], utc=True).dt.floor("h")
            merged = merged.merge(extra_df[["timestamp", col]], on="timestamp", how="left")
        else:
            merged[col] = np.nan

    if not gb_prices_df.empty:
        gb_prices_df = gb_prices_df.copy()
        gb_prices_df["timestamp"] = pd.to_datetime(gb_prices_df["timestamp"], utc=True).dt.floor("h")
        merged = merged.merge(gb_prices_df[["timestamp", "price_gbp_mwh"]], on="timestamp", how="left")
    else:
        merged["price_gbp_mwh"] = np.nan

    # ── Fill missing demand/generation from physics-based estimates ───────
    peak_demand = MARKET_PEAK_DEMAND.get(market_code, 50000.0)
    demand_baseline = peak_demand * 0.64
    wind_installed = MARKET_WIND_INSTALLED.get(market_code, 5000.0)
    solar_installed = MARKET_SOLAR_INSTALLED.get(market_code, 3000.0)
    regional_basis = MARKET_REGIONAL_BASIS.get(market_code, 0.0)

    for idx, row in merged.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        if pd.isna(row.get("demand_mw")):
            merged.at[idx, "demand_mw"] = synthetic_demand(
                ts.hour, ts.dayofweek, float(row["temperature_c"]),
                demand_baseline, ts.month, rng,
            )
        if pd.isna(row.get("wind_mw")):
            merged.at[idx, "wind_mw"] = _wind_gen(float(row["wind_speed"]), wind_installed)
        if pd.isna(row.get("solar_mw")):
            merged.at[idx, "solar_mw"] = _solar_gen(
                float(row.get("direct_radiation", 0.0)), solar_installed, ts.hour
            )

    # ── Check what's already in DB (avoid duplicates) ────────────────────
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

        # Price: use ELEXON directly for GB, else compute from fundamentals
        if is_gb and not pd.isna(row.get("price_gbp_mwh")):
            price = float(row["price_gbp_mwh"]) * gbp_usd
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
            if "prices" not in sources:
                sources["prices"] = "computed-fundamentals"

        db.add(PricePoint(
            market_id=market.id,
            timestamp=ts,
            horizon_type="spot",
            price_value=price,
            source=sources.get("prices", "computed"),
        ))
        db.add(WeatherPoint(
            market_id=market.id,
            timestamp=ts,
            temperature_c=temp_c,
            wind_speed=wind_speed,
            wind_generation_estimate=wind_mw,
            solar_generation_estimate=solar_mw,
            precipitation=precip,
            source="open-meteo" if sources.get("weather") == "open-meteo" else "synthetic",
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
    logger.info(
        "Market %s: inserted %d new data points. Sources: %s",
        market_code, inserted, sources,
    )
    return sources
