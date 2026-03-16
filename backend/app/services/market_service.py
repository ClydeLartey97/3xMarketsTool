from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Market


def list_markets(db: Session) -> list[Market]:
    return list(db.scalars(select(Market).order_by(Market.name)).all())


def get_market_by_id(db: Session, market_id: int) -> Market | None:
    return db.get(Market, market_id)


def get_market_by_code(db: Session, market_code: str) -> Market | None:
    return db.scalar(select(Market).where(Market.code == market_code))
