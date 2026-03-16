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
