from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.schema import require_database_schema
from app.db.session import SessionLocal, engine
from app.services.market_stream import publish_market_message_sync

logger = logging.getLogger(__name__)
settings = get_settings()


def refresh_all_markets() -> dict[str, Any]:
    """Refresh real data + RSS news for every configured market."""
    from app.ingestion.news_rss import ingest_rss_feeds
    from app.ingestion.real_data import populate_market_real_data
    from app.models import Market, PricePoint
    from app.services.alert_service import refresh_alerts_for_market
    from app.services.forecast_service import invalidate_forecast_cache, run_forecast_for_market

    require_database_schema(engine)
    failures: list[str] = []
    refreshed = 0
    rss_inserted = 0
    with SessionLocal() as db:
        markets = list(db.scalars(select(Market).order_by(Market.code.asc())).all())
        for market in markets:
            try:
                populate_market_real_data(
                    db=db,
                    market=market,
                    market_code=market.code,
                    eia_api_key=settings.eia_api_key,
                    days=1,
                )
                invalidate_forecast_cache(market.code)
                run_forecast_for_market(db, market, horizon_hours=48, use_cache=False)
                latest_price = db.scalar(
                    select(PricePoint)
                    .where(PricePoint.market_id == market.id)
                    .order_by(PricePoint.timestamp.desc())
                    .limit(1)
                )
                if latest_price:
                    publish_market_message_sync(
                        market.code,
                        {
                            "type": "price_tick",
                            "timestamp": latest_price.timestamp,
                            "price_value": latest_price.price_value,
                            "currency": latest_price.currency,
                            "source": latest_price.source,
                        },
                    )
                alerts = refresh_alerts_for_market(db, market.id)
                if alerts:
                    latest_alert = max(alerts, key=lambda item: item.created_at)
                    publish_market_message_sync(
                        market.code,
                        {
                            "type": "alert",
                            "alert_id": latest_alert.id,
                            "title": latest_alert.title,
                            "severity": latest_alert.severity,
                            "created_at": latest_alert.created_at,
                        },
                    )
                publish_market_message_sync(
                    market.code,
                    {
                        "type": "forecast_revision",
                        "reason": "market_refresh",
                        "refreshed_at": datetime.now(timezone.utc),
                    },
                )
                refreshed += 1
            except Exception as exc:
                failures.append(market.code)
                logger.exception("Refresh failed for %s: %s", market.code, exc)

        try:
            rss_inserted = ingest_rss_feeds(db, max_per_feed=4)
            if rss_inserted:
                for market in markets:
                    publish_market_message_sync(
                        market.code,
                        {
                            "type": "new_event",
                            "count": rss_inserted,
                            "created_at": datetime.now(timezone.utc),
                        },
                    )
        except Exception as exc:
            logger.exception("RSS refresh failed: %s", exc)

    if failures and refreshed == 0:
        raise RuntimeError(f"all market refreshes failed: {', '.join(failures)}")
    result = {
        "refreshed": refreshed,
        "failed": failures,
        "rss_inserted": rss_inserted,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Background market refresh complete: %s", result)
    return result


def fill_risk_assessment_pnl() -> dict[str, Any]:
    from app.services.risk_calibration import fill_matured_risk_assessment_logs

    require_database_schema(engine)
    with SessionLocal() as db:
        updated = fill_matured_risk_assessment_logs(db)
    if updated:
        publish_market_message_sync(
            "ALL",
            {
                "type": "risk_recomputed",
                "updated": updated,
                "created_at": datetime.now(timezone.utc),
            },
        )
    result = {"updated": updated, "completed_at": datetime.now(timezone.utc).isoformat()}
    logger.info("Filled realized P&L for %d matured risk assessments.", updated)
    return result


def run_nightly_backtest() -> dict[str, Any]:
    from scripts.backtest import run_backtest_reports

    paths = run_backtest_reports(markets=None, lookback_days=365, compare="gbr")
    result = {
        "reports": [Path(path).name for path in paths],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Nightly backtest complete: %s", result)
    return result
