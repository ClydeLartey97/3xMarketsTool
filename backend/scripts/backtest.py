"""Run a walk-forward backtest for one or more markets and write a JSON report.

Usage:
    python3 scripts/backtest.py --market GB_POWER --lookback-days 365
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

from app.db.base import Base
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest runner")
    parser.add_argument("--market", action="append", dest="markets", help="Market code; repeatable.")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=7)
    parser.add_argument("--step-hours", type=int, default=24)
    parser.add_argument("--horizon-hours", type=int, default=24)
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    since = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)

    with SessionLocal() as db:
        markets = list(db.scalars(select(Market).order_by(Market.code.asc())).all())
        if args.markets:
            markets = [m for m in markets if m.code in set(args.markets)]
        for market in markets:
            prices, weather, demand, events = _load_for_market(db, market, since)
            if len(prices) < 24 * (args.train_days + args.test_days):
                print(f"{market.code}: not enough history ({len(prices)}h); skipping")
                continue
            events_frame = pd.DataFrame(events_as_feature_frame(events))
            feature_frame = build_feature_frame_from_db(
                prices=prices, weather=weather, demand=demand, events_frame=events_frame,
            )
            result = walk_forward_backtest(
                feature_frame,
                train_window_hours=args.train_days * 24,
                test_window_hours=args.test_days * 24,
                step_hours=args.step_hours,
                horizon_hours=args.horizon_hours,
            )
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            out_path = REPORTS_DIR / f"backtest_{market.code}_{stamp}.json"
            payload = {
                "market_code": market.code,
                "market_name": market.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "lookback_days": args.lookback_days,
                **result.to_dict(),
            }
            out_path.write_text(json.dumps(payload, indent=2))
            print(
                f"{market.code}: model RMSE={result.metrics.get('rmse')}  "
                f"vs persistence_24h RMSE={result.vs_baselines.get('persistence_24h',{}).get('rmse')}  "
                f"calibrated={result.calibration.get('well_calibrated')}  "
                f"→ {out_path.name}"
            )


if __name__ == "__main__":
    main()
