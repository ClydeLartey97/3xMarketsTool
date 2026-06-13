from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from arq import Retry, cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.observability import configure_logging
from app.workers.jobs import (
    compute_radar_snapshot,
    fill_risk_assessment_pnl,
    refresh_all_markets,
    run_nightly_backtest,
)

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)


def _minute_schedule(interval_minutes: int) -> int | set[int]:
    interval = max(1, int(interval_minutes))
    if interval >= 60:
        return 0
    return set(range(0, 60, interval))


def _retry_delay(ctx: dict[str, Any]) -> int:
    job_try = max(1, int(ctx.get("job_try", 1)))
    return min(3600, 30 * (2 ** (job_try - 1)))


async def _run_with_retry(ctx: dict[str, Any], label: str, fn: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(fn)
    except Exception as exc:
        defer = _retry_delay(ctx)
        logger.exception("%s failed; retrying in %ss", label, defer)
        raise Retry(defer=defer) from exc


async def refresh_all_markets_job(ctx: dict[str, Any]) -> Any:
    return await _run_with_retry(ctx, "market_refresh", refresh_all_markets)


async def fill_risk_assessment_pnl_job(ctx: dict[str, Any]) -> Any:
    return await _run_with_retry(ctx, "risk_assessment_pnl_fill", fill_risk_assessment_pnl)


async def nightly_backtest_job(ctx: dict[str, Any]) -> Any:
    return await _run_with_retry(ctx, "nightly_backtest", run_nightly_backtest)


async def compute_radar_snapshot_job(ctx: dict[str, Any]) -> Any:
    return await _run_with_retry(ctx, "radar_snapshot", compute_radar_snapshot)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [
        refresh_all_markets_job,
        fill_risk_assessment_pnl_job,
        nightly_backtest_job,
        compute_radar_snapshot_job,
    ]
    cron_jobs = [
        cron(
            refresh_all_markets_job,
            name="market_refresh",
            minute=_minute_schedule(settings.data_refresh_interval_minutes),
            second=0,
            timeout=30 * 60,
            max_tries=5,
        ),
        cron(
            fill_risk_assessment_pnl_job,
            name="risk_assessment_pnl_fill",
            minute=5,
            second=0,
            timeout=10 * 60,
            max_tries=5,
        ),
        cron(
            nightly_backtest_job,
            name="nightly_backtest",
            hour=2,
            minute=15,
            second=0,
            timeout=2 * 60 * 60,
            max_tries=5,
        ),
        cron(
            compute_radar_snapshot_job,
            name="radar_snapshot",
            minute=_minute_schedule(settings.data_refresh_interval_minutes),
            second=30,  # just after the market refresh on the same minute cadence
            timeout=10 * 60,
            max_tries=3,
        ),
    ]
    max_jobs = 2
    keep_result = 3600
