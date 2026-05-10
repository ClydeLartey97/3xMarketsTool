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
    assert {"kind", "thesis_text"} <= columns
