from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ingestion.real_data import backfill_market
from app.models import Market


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical market data.")
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--market", action="append", dest="markets", help="Market code to backfill. Repeatable.")
    args = parser.parse_args()

    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.markets:
            market_codes = args.markets
        else:
            market_codes = list(db.scalars(select(Market.code).order_by(Market.code.asc())).all())

        for market_code in market_codes:
            summary = backfill_market(
                market_code,
                lookback_days=args.lookback_days,
                db=db,
                eia_api_key=settings.eia_api_key,
            )
            db.commit()
            print(
                f"{summary['market']}: inserted={summary['inserted']} "
                f"price_points={summary['price_points_after']} "
                f"real_price_points={summary['real_price_points_after']} "
                f"sources={summary['sources']}"
            )


if __name__ == "__main__":
    main()
