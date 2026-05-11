"""baseline schema

Revision ID: 20260511_0001
Revises:
Create Date: 2026-05-11 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("commodity_type", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_markets_code", "markets", ["code"], unique=True)
    op.create_index("ix_markets_id", "markets", ["id"], unique=False)

    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("processed_status", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("organisation", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_market_id", "alerts", ["market_id"], unique=False)

    op.create_table(
        "demand_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("demand_mw", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demand_points_market_id", "demand_points", ["market_id"], unique=False)
    op.create_index("ix_demand_points_timestamp", "demand_points", ["timestamp"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_region", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("capacity_impact_mw", sa.Float(), nullable=True),
        sa.Column("zone", sa.String(length=128), nullable=True),
        sa.Column("node", sa.String(length=128), nullable=True),
        sa.Column("magnitude_mw", sa.Float(), nullable=True),
        sa.Column("duration_hours_estimate", sa.Float(), nullable=True),
        sa.Column("duration_hours_p10", sa.Float(), nullable=True),
        sa.Column("duration_hours_p90", sa.Float(), nullable=True),
        sa.Column("analogue_event_ids", sa.JSON(), nullable=False),
        sa.Column("classifier_version", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("price_direction", sa.String(length=32), nullable=False),
        sa.Column("estimated_price_impact_pct", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_event_type", "events", ["event_type"], unique=False)

    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("forecast_for_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_estimate", sa.Float(), nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=False),
        sa.Column("upper_bound", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("spike_probability", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("rationale_summary", sa.Text(), nullable=False),
        sa.Column("feature_snapshot_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecasts_forecast_for_timestamp", "forecasts", ["forecast_for_timestamp"], unique=False)
    op.create_index("ix_forecasts_market_id", "forecasts", ["market_id"], unique=False)

    op.create_table(
        "price_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_type", sa.String(length=32), nullable=False),
        sa.Column("price_value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_points_market_id", "price_points", ["market_id"], unique=False)
    op.create_index("ix_price_points_timestamp", "price_points", ["timestamp"], unique=False)

    op.create_table(
        "risk_assessment_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("position_gbp", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("risk_gbp", sa.Float(), nullable=False),
        sa.Column("likely_gbp", sa.Float(), nullable=False),
        sa.Column("upside_gbp", sa.Float(), nullable=False),
        sa.Column("realized_pnl_gbp", sa.Float(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("thesis_text", sa.Text(), nullable=True),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_assessment_log_is_open", "risk_assessment_log", ["is_open"], unique=False)
    op.create_index("ix_risk_assessment_log_kind", "risk_assessment_log", ["kind"], unique=False)
    op.create_index("ix_risk_assessment_log_market_id", "risk_assessment_log", ["market_id"], unique=False)
    op.create_index("ix_risk_assessment_log_timestamp", "risk_assessment_log", ["timestamp"], unique=False)

    op.create_table(
        "user_watchlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_watchlists_market_id", "user_watchlists", ["market_id"], unique=False)
    op.create_index("ix_user_watchlists_user_id", "user_watchlists", ["user_id"], unique=False)

    op.create_table(
        "weather_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("wind_speed", sa.Float(), nullable=False),
        sa.Column("wind_generation_estimate", sa.Float(), nullable=False),
        sa.Column("solar_generation_estimate", sa.Float(), nullable=False),
        sa.Column("precipitation", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weather_points_market_id", "weather_points", ["market_id"], unique=False)
    op.create_index("ix_weather_points_timestamp", "weather_points", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_weather_points_timestamp", table_name="weather_points")
    op.drop_index("ix_weather_points_market_id", table_name="weather_points")
    op.drop_table("weather_points")
    op.drop_index("ix_user_watchlists_user_id", table_name="user_watchlists")
    op.drop_index("ix_user_watchlists_market_id", table_name="user_watchlists")
    op.drop_table("user_watchlists")
    op.drop_index("ix_risk_assessment_log_timestamp", table_name="risk_assessment_log")
    op.drop_index("ix_risk_assessment_log_market_id", table_name="risk_assessment_log")
    op.drop_index("ix_risk_assessment_log_kind", table_name="risk_assessment_log")
    op.drop_index("ix_risk_assessment_log_is_open", table_name="risk_assessment_log")
    op.drop_table("risk_assessment_log")
    op.drop_index("ix_price_points_timestamp", table_name="price_points")
    op.drop_index("ix_price_points_market_id", table_name="price_points")
    op.drop_table("price_points")
    op.drop_index("ix_forecasts_market_id", table_name="forecasts")
    op.drop_index("ix_forecasts_forecast_for_timestamp", table_name="forecasts")
    op.drop_table("forecasts")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_demand_points_timestamp", table_name="demand_points")
    op.drop_index("ix_demand_points_market_id", table_name="demand_points")
    op.drop_table("demand_points")
    op.drop_index("ix_alerts_market_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("users")
    op.drop_index("ix_news_articles_published_at", table_name="news_articles")
    op.drop_table("news_articles")
    op.drop_index("ix_markets_id", table_name="markets")
    op.drop_index("ix_markets_code", table_name="markets")
    op.drop_table("markets")
