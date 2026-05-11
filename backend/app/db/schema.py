from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


REQUIRED_TABLES = {
    "alerts",
    "demand_points",
    "events",
    "forecasts",
    "markets",
    "news_articles",
    "price_points",
    "risk_assessment_log",
    "user_watchlists",
    "users",
    "weather_points",
}


def database_has_schema(engine: Engine) -> bool:
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
    return REQUIRED_TABLES.issubset(table_names)


def require_database_schema(engine: Engine) -> None:
    if database_has_schema(engine):
        return
    raise RuntimeError(
        "Database schema is not initialized. Run `alembic -c alembic.ini upgrade head` "
        "from the repository root before starting the app or scripts."
    )
