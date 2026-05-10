from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def apply_sqlite_compat_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        if "risk_assessment_log" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("risk_assessment_log")}
        if "kind" not in columns:
            connection.execute(
                text("ALTER TABLE risk_assessment_log ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'auto'")
            )
        if "thesis_text" not in columns:
            connection.execute(text("ALTER TABLE risk_assessment_log ADD COLUMN thesis_text TEXT"))
