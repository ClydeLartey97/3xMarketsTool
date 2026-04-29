from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ingestion.seeds import seed_database

logger = logging.getLogger(__name__)
settings = get_settings()

_scheduler: BackgroundScheduler | None = None
_last_refresh: dict[str, datetime] = {}


def _refresh_all_markets() -> None:
    """Background job: refresh real data + news for all markets."""
    try:
        from sqlalchemy import select
        from app.ingestion.real_data import populate_market_real_data
        from app.ingestion.news_rss import ingest_rss_feeds
        from app.models import Market
        from app.services.forecast_service import invalidate_forecast_cache

        with SessionLocal() as db:
            markets = list(db.scalars(select(Market)).all())
            for market in markets:
                try:
                    populate_market_real_data(
                        db=db,
                        market=market,
                        market_code=market.code,
                        eia_api_key=settings.eia_api_key,
                        days=1,  # only fetch the most recent day on refresh
                    )
                    invalidate_forecast_cache(market.code)
                except Exception as exc:
                    logger.error("Refresh failed for %s: %s", market.code, exc)

            try:
                n = ingest_rss_feeds(db, max_per_feed=4)
                logger.info("RSS refresh: %d new articles", n)
            except Exception as exc:
                logger.error("RSS refresh failed: %s", exc)

        _last_refresh["all"] = datetime.now(timezone.utc)
        logger.info("Background market refresh complete.")
    except Exception as exc:
        logger.error("Background refresh error: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _scheduler
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)

    # Start background scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _refresh_all_markets,
        "interval",
        minutes=settings.data_refresh_interval_minutes,
        id="market_refresh",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started. Market refresh every %d minutes.",
        settings.data_refresh_interval_minutes,
    )

    yield

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_v1_prefix)
