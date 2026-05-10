from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def apply_sqlite_compat_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "risk_assessment_log" in table_names:
            columns = {column["name"] for column in inspector.get_columns("risk_assessment_log")}
            if "kind" not in columns:
                connection.execute(
                    text("ALTER TABLE risk_assessment_log ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'auto'")
                )
            if "thesis_text" not in columns:
                connection.execute(text("ALTER TABLE risk_assessment_log ADD COLUMN thesis_text TEXT"))
            if "is_open" not in columns:
                connection.execute(
                    text("ALTER TABLE risk_assessment_log ADD COLUMN is_open BOOLEAN NOT NULL DEFAULT 1")
                )
            if "closed_at" not in columns:
                connection.execute(text("ALTER TABLE risk_assessment_log ADD COLUMN closed_at DATETIME"))

        if "events" not in table_names:
            return
        event_columns = {column["name"] for column in inspector.get_columns("events")}
        event_column_sql = {
            "zone": "ALTER TABLE events ADD COLUMN zone VARCHAR(128)",
            "node": "ALTER TABLE events ADD COLUMN node VARCHAR(128)",
            "magnitude_mw": "ALTER TABLE events ADD COLUMN magnitude_mw FLOAT",
            "duration_hours_estimate": "ALTER TABLE events ADD COLUMN duration_hours_estimate FLOAT",
            "duration_hours_p10": "ALTER TABLE events ADD COLUMN duration_hours_p10 FLOAT",
            "duration_hours_p90": "ALTER TABLE events ADD COLUMN duration_hours_p90 FLOAT",
            "analogue_event_ids": "ALTER TABLE events ADD COLUMN analogue_event_ids JSON NOT NULL DEFAULT '[]'",
            "classifier_version": (
                "ALTER TABLE events ADD COLUMN classifier_version VARCHAR(64) NOT NULL DEFAULT 'heuristic-v1'"
            ),
        }
        for column, sql in event_column_sql.items():
            if column not in event_columns:
                connection.execute(text(sql))
