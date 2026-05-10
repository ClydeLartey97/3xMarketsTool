from __future__ import annotations

from collections.abc import Callable

from app.forecasting.base import ForecastModel
from app.forecasting.model import GradientBoostingForecastModel
from app.forecasting.naive import NaivePersistence24hForecastModel


def _chronos_factory() -> ForecastModel:
    from app.forecasting.chronos_model import ChronosForecastModel

    return ChronosForecastModel()


forecaster_registry: dict[str, Callable[[], ForecastModel]] = {
    "gbr": GradientBoostingForecastModel,
    "chronos": _chronos_factory,
    "naive_persistence_24h": NaivePersistence24hForecastModel,
}


def create_forecaster(name: str) -> ForecastModel:
    normalized_name = name.strip().lower()
    factory = forecaster_registry.get(normalized_name)
    if factory is None:
        available = ", ".join(sorted(forecaster_registry))
        raise ValueError(f"Unknown forecaster '{name}'. Available forecasters: {available}")
    return factory()
