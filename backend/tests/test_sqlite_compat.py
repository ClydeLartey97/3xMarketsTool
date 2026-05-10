from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.db.compat import apply_sqlite_compat_migrations


def test_sqlite_compat_adds_risk_log_decision_columns() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE risk_assessment_log (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    market_id INTEGER NOT NULL,
                    position_gbp FLOAT NOT NULL,
                    direction VARCHAR(8) NOT NULL,
                    horizon_hours INTEGER NOT NULL,
                    risk_gbp FLOAT NOT NULL,
                    likely_gbp FLOAT NOT NULL,
                    upside_gbp FLOAT NOT NULL,
                    realized_pnl_gbp FLOAT
                )
                """
            )
        )

    apply_sqlite_compat_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("risk_assessment_log")}
    assert {"kind", "thesis_text", "is_open", "closed_at"} <= columns


def test_sqlite_compat_adds_structured_event_columns() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY,
                    event_type VARCHAR(64) NOT NULL,
                    title VARCHAR(256) NOT NULL,
                    description TEXT NOT NULL,
                    affected_region VARCHAR(128) NOT NULL,
                    asset_type VARCHAR(64) NOT NULL,
                    capacity_impact_mw FLOAT,
                    severity VARCHAR(32) NOT NULL,
                    confidence FLOAT NOT NULL,
                    price_direction VARCHAR(32) NOT NULL,
                    rationale TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    apply_sqlite_compat_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("events")}
    assert {
        "zone",
        "node",
        "magnitude_mw",
        "duration_hours_estimate",
        "duration_hours_p10",
        "duration_hours_p90",
        "analogue_event_ids",
        "classifier_version",
    } <= columns
