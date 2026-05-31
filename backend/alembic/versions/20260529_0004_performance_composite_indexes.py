"""performance composite indexes

Adds composite (market_id, timestamp) and similar indexes to support the
hot query patterns identified in docs/PERFORMANCE_PRESERVATION_PLAN.md
(Phase 1.1). All indexes are additive — existing single-column indexes
are kept so query planners that prefer them are not surprised.

Revision ID: 20260529_0004
Revises: 20260511_0003
Create Date: 2026-05-29 00:00:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "20260529_0004"
down_revision = "20260511_0003"
branch_labels = None
depends_on = None


# (index_name, table, columns)
_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_price_points_market_id_timestamp", "price_points", ["market_id", "timestamp"]),
    ("ix_forecasts_market_id_forecast_for_timestamp", "forecasts", ["market_id", "forecast_for_timestamp"]),
    ("ix_events_market_id_created_at", "events", ["market_id", "created_at"]),
    ("ix_events_article_id", "events", ["article_id"]),
    ("ix_weather_points_market_id_timestamp", "weather_points", ["market_id", "timestamp"]),
    ("ix_demand_points_market_id_timestamp", "demand_points", ["market_id", "timestamp"]),
    ("ix_alerts_market_id_created_at", "alerts", ["market_id", "created_at"]),
    ("ix_news_articles_published_at", "news_articles", ["published_at"]),
    (
        "ix_risk_log_market_id_timestamp",
        "risk_assessment_log",
        ["market_id", "timestamp"],
    ),
    (
        "ix_risk_log_user_id_market_id_timestamp",
        "risk_assessment_log",
        ["user_id", "market_id", "timestamp"],
    ),
    (
        "ix_risk_log_user_id_is_open_timestamp",
        "risk_assessment_log",
        ["user_id", "is_open", "timestamp"],
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = _make_inspector(bind)
    for index_name, table, columns in _INDEXES:
        if not _table_exists(inspector, table):
            continue
        if _index_exists(inspector, table, index_name):
            continue
        op.create_index(index_name, table, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = _make_inspector(bind)
    for index_name, table, _columns in reversed(_INDEXES):
        if not _table_exists(inspector, table):
            continue
        if not _index_exists(inspector, table, index_name):
            continue
        op.drop_index(index_name, table_name=table)


def _make_inspector(bind):
    from sqlalchemy import inspect

    return inspect(bind)


def _table_exists(inspector, table: str) -> bool:
    try:
        return table in inspector.get_table_names()
    except Exception:  # noqa: BLE001 — defensive on exotic dialects
        return True


def _index_exists(inspector, table: str, index_name: str) -> bool:
    try:
        existing = {idx.get("name") for idx in inspector.get_indexes(table)}
    except Exception:  # noqa: BLE001
        return False
    return index_name in existing
