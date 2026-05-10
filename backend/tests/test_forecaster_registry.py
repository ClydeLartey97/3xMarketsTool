from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.forecasting.registry import create_forecaster, forecaster_registry
from app.models import Market
from app.services.forecast_service import invalidate_forecast_cache, run_forecast_for_market


def test_forecaster_registry_returns_fresh_instances() -> None:
    assert {"gbr", "chronos", "naive_persistence_24h"} <= set(forecaster_registry)

    first = create_forecaster("gbr")
    second = create_forecaster("gbr")
    assert first is not second
    assert first.model_name == second.model_name

    naive_first = create_forecaster("naive_persistence_24h")
    naive_second = create_forecaster("naive_persistence_24h")
    assert naive_first is not naive_second
    assert naive_first.model_name == "naive-persistence-24h-v1"


def test_switching_active_forecaster_changes_model_version(db_session, monkeypatch) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None

    monkeypatch.setenv("ACTIVE_FORECASTER", "gbr")
    get_settings.cache_clear()
    invalidate_forecast_cache()
    gbr_forecasts, _ = run_forecast_for_market(db_session, market, horizon_hours=1, use_cache=False)
    assert gbr_forecasts
    gbr_model_version = gbr_forecasts[0].model_version

    monkeypatch.setenv("ACTIVE_FORECASTER", "naive_persistence_24h")
    get_settings.cache_clear()
    invalidate_forecast_cache()
    naive_forecasts, _ = run_forecast_for_market(db_session, market, horizon_hours=1, use_cache=False)
    assert naive_forecasts
    naive_model_version = naive_forecasts[0].model_version

    get_settings.cache_clear()
    assert gbr_model_version != naive_model_version
    assert naive_model_version == "naive-persistence-24h-v1"
