from __future__ import annotations


def normalize_database_url(database_url: str) -> str:
    """Return a SQLAlchemy URL with an explicit modern Postgres driver."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")
