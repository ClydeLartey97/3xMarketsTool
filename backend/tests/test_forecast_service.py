from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Forecast, Market, PricePoint
from app.services import forecast_service
from app.services.forecast_service import invalidate_forecast_cache, run_forecast_for_market


def test_run_forecast_for_market(db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None

    forecasts, metrics = run_forecast_for_market(db_session, market, horizon_hours=12)

    assert len(forecasts) == 12
    assert all(f.lower_bound <= f.point_estimate <= f.upper_bound for f in forecasts)
    assert metrics["mae"] >= 0
    assert metrics["rmse"] >= 0


def test_forecasts_differ_across_markets(db_session) -> None:
    ercot = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    gb = db_session.scalar(select(Market).where(Market.code == "GB_POWER"))
    assert ercot is not None
    assert gb is not None

    ercot_forecasts, _ = run_forecast_for_market(db_session, ercot, horizon_hours=24)
    gb_forecasts, _ = run_forecast_for_market(db_session, gb, horizon_hours=24)

    ercot_curve = [round(item.point_estimate, 2) for item in ercot_forecasts]
    gb_curve = [round(item.point_estimate, 2) for item in gb_forecasts]
    assert ercot_curve != gb_curve


def test_forecast_cache_respects_requested_horizon(db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None

    short_forecasts, _ = run_forecast_for_market(db_session, market, horizon_hours=12)
    longer_forecasts, _ = run_forecast_for_market(db_session, market, horizon_hours=24)
    repeated_short, _ = run_forecast_for_market(db_session, market, horizon_hours=12)

    assert len(short_forecasts) == 12
    assert len(longer_forecasts) == 24
    assert len(repeated_short) == 12


def test_run_forecast_uses_stored_curve_when_rebuild_fails(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    latest_price_ts = db_session.scalar(
        select(PricePoint.timestamp)
        .where(PricePoint.market_id == market.id)
        .order_by(PricePoint.timestamp.desc())
        .limit(1)
    )
    assert latest_price_ts is not None
    stored = list(
        db_session.scalars(
            select(Forecast)
            .where(Forecast.market_id == market.id)
            .order_by(Forecast.forecast_for_timestamp.asc())
            .limit(12)
        ).all()
    )
    assert len(stored) == 12
    for index, forecast in enumerate(stored):
        forecast.forecast_for_timestamp = latest_price_ts - timedelta(hours=12 - index)
    db_session.commit()
    invalidate_forecast_cache(market.code)

    def fail_rebuild(*args, **kwargs):
        raise RuntimeError("forecast rebuild unavailable")

    monkeypatch.setattr(forecast_service, "_build_forecast_for_market", fail_rebuild)

    forecasts, metrics = run_forecast_for_market(db_session, market, horizon_hours=12, use_cache=True)

    assert len(forecasts) == 12
    assert metrics["directional_accuracy"] >= 0
