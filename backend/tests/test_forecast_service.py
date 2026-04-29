from sqlalchemy import select

from app.models import Market
from app.services.forecast_service import run_forecast_for_market


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
