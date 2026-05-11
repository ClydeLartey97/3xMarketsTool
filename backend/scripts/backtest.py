"""Run a walk-forward backtest for one or more markets and write a JSON report.

Usage:
    python3 scripts/backtest.py --market GB_POWER --lookback-days 365
    python3 scripts/backtest.py --market GB_POWER --compare gbr,chronos
    python3 scripts/backtest.py  # all markets
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.db.schema import require_database_schema
from app.db.session import SessionLocal, engine
from app.forecasting.backtest import (
    build_feature_frame_from_db,
    walk_forward_backtest,
)
from app.models import DemandPoint, Event, Market, PricePoint, WeatherPoint
from app.services.event_service import events_as_feature_frame


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def _load_for_market(db, market: Market, since: datetime):
    prices = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id, PricePoint.timestamp >= since)
            .order_by(PricePoint.timestamp.asc())
        ).all()
    )
    weather = list(
        db.scalars(
            select(WeatherPoint)
            .where(WeatherPoint.market_id == market.id, WeatherPoint.timestamp >= since)
            .order_by(WeatherPoint.timestamp.asc())
        ).all()
    )
    demand = list(
        db.scalars(
            select(DemandPoint)
            .where(DemandPoint.market_id == market.id, DemandPoint.timestamp >= since)
            .order_by(DemandPoint.timestamp.asc())
        ).all()
    )
    events = list(
        db.scalars(
            select(Event)
            .where(Event.market_id == market.id)
            .order_by(Event.created_at.asc())
        ).all()
    )
    return prices, weather, demand, events


def run_backtest_reports(
    *,
    markets: list[str] | None = None,
    lookback_days: int = 365,
    train_days: int = 60,
    test_days: int = 7,
    step_hours: int = 24,
    horizon_hours: int = 24,
    compare: str | list[str] = "gbr",
) -> list[Path]:
    forecaster_names = [name.strip() for name in compare.split(",") if name.strip()] if isinstance(compare, str) else compare
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    require_database_schema(engine)
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    written: list[Path] = []

    with SessionLocal() as db:
        market_rows = list(db.scalars(select(Market).order_by(Market.code.asc())).all())
        if markets:
            market_rows = [m for m in market_rows if m.code in set(markets)]
        for market in market_rows:
            prices, weather, demand, events = _load_for_market(db, market, since)
            if len(prices) < 24 * (train_days + test_days):
                print(f"{market.code}: not enough history ({len(prices)}h); skipping")
                continue
            events_frame = pd.DataFrame(events_as_feature_frame(events))
            feature_frame = build_feature_frame_from_db(
                prices=prices, weather=weather, demand=demand, events_frame=events_frame,
            )
            result = walk_forward_backtest(
                feature_frame,
                train_window_hours=train_days * 24,
                test_window_hours=test_days * 24,
                step_hours=step_hours,
                horizon_hours=horizon_hours,
                forecaster_names=forecaster_names,
            )
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            out_path = REPORTS_DIR / f"backtest_{market.code}_{stamp}.json"
            payload = {
                "market_code": market.code,
                "market_name": market.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "lookback_days": lookback_days,
                **result.to_dict(),
            }
            out_path.write_text(json.dumps(payload, indent=2))
            written.append(out_path)
            print(
                f"{market.code}: model RMSE={result.metrics.get('rmse')}  "
                f"vs persistence_24h RMSE={result.vs_baselines.get('persistence_24h',{}).get('rmse')}  "
                f"forecasters={','.join(result.vs_forecasters.keys()) or 'none'}  "
                f"calibrated={result.calibration.get('well_calibrated')}  "
                f"→ {out_path.name}"
            )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest runner")
    parser.add_argument("--market", action="append", dest="markets", help="Market code; repeatable.")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=7)
    parser.add_argument("--step-hours", type=int, default=24)
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument(
        "--compare",
        default="gbr",
        help="Comma-separated forecaster names to compare, e.g. gbr,chronos.",
    )
    args = parser.parse_args()
    run_backtest_reports(
        markets=args.markets,
        lookback_days=args.lookback_days,
        train_days=args.train_days,
        test_days=args.test_days,
        step_hours=args.step_hours,
        horizon_hours=args.horizon_hours,
        compare=args.compare,
    )


if __name__ == "__main__":
    main()
