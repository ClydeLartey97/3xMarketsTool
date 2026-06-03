from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Market, RiskAssessmentLog
from app.services.risk_calibration import fill_matured_risk_assessment_logs


def _predicted_percentile(row: RiskAssessmentLog) -> float | None:
    if row.realized_pnl_gbp is None:
        return None
    realized = float(row.realized_pnl_gbp)
    lower = -float(row.risk_gbp)
    median = float(row.likely_gbp)
    upper = float(row.upside_gbp)
    if realized <= lower:
        return 5.0
    if realized >= upper:
        return 95.0
    if realized <= median:
        span = max(1e-6, median - lower)
        return round(5.0 + ((realized - lower) / span) * 45.0, 1)
    span = max(1e-6, upper - median)
    return round(50.0 + ((realized - median) / span) * 45.0, 1)


def _decision_read(row: RiskAssessmentLog, market: Market) -> dict[str, Any]:
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "market_id": market.id,
        "market_code": market.code,
        "market_name": market.name,
        "user_id": row.user_id,
        "position_gbp": row.position_gbp,
        "direction": row.direction,
        "horizon_hours": row.horizon_hours,
        "risk_gbp": row.risk_gbp,
        "likely_gbp": row.likely_gbp,
        "upside_gbp": row.upside_gbp,
        "realized_pnl_gbp": row.realized_pnl_gbp,
        "predicted_percentile": _predicted_percentile(row),
        "thesis_text": row.thesis_text or "",
        "is_open": bool(row.is_open),
        "closed_at": row.closed_at,
    }


def create_decision(db: Session, payload: Any, user_id: int) -> dict[str, Any]:
    market = db.scalar(select(Market).where(Market.code == payload.market_code))
    if not market:
        raise ValueError(f"unknown market {payload.market_code}")
    row = RiskAssessmentLog(
        timestamp=datetime.now(timezone.utc),
        market_id=market.id,
        user_id=user_id,
        position_gbp=float(payload.position_gbp),
        direction=payload.direction,
        horizon_hours=int(payload.horizon_hours),
        risk_gbp=float(payload.risk_gbp),
        likely_gbp=float(payload.likely_gbp),
        upside_gbp=float(payload.upside_gbp),
        realized_pnl_gbp=None,
        kind="diary",
        thesis_text=payload.thesis_text,
        is_open=bool(payload.is_open),
        closed_at=None if payload.is_open else datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _decision_read(row, market)


def list_decisions(db: Session, market_id: int | None = None, user_id: int | None = None) -> list[dict[str, Any]]:
    fill_matured_risk_assessment_logs(
        db,
        kind="diary",
        market_id=market_id,
        user_id=user_id,
        limit=200,
    )
    stmt = (
        select(RiskAssessmentLog, Market)
        .join(Market, Market.id == RiskAssessmentLog.market_id)
        .where(RiskAssessmentLog.kind == "diary")
        .order_by(RiskAssessmentLog.timestamp.desc())
    )
    if market_id is not None:
        stmt = stmt.where(RiskAssessmentLog.market_id == market_id)
    if user_id is not None:
        stmt = stmt.where(RiskAssessmentLog.user_id == user_id)
    return [_decision_read(row, market) for row, market in db.execute(stmt).all()]


def update_decision(db: Session, decision_id: int, payload: Any, user_id: int) -> dict[str, Any]:
    row = db.scalar(
        select(RiskAssessmentLog).where(
            RiskAssessmentLog.id == decision_id,
            RiskAssessmentLog.kind == "diary",
            RiskAssessmentLog.user_id == user_id,
        )
    )
    if not row:
        raise ValueError("decision not found")

    if payload.thesis_text is not None:
        row.thesis_text = payload.thesis_text
    if payload.is_open is not None:
        is_open = bool(payload.is_open)
        row.is_open = is_open
        row.closed_at = None if is_open else datetime.now(timezone.utc)

    db.commit()
    db.refresh(row)
    market = db.get(Market, row.market_id)
    if not market:
        raise ValueError("decision market not found")
    return _decision_read(row, market)


def delete_decision(db: Session, decision_id: int, user_id: int) -> None:
    result = db.execute(
        delete(RiskAssessmentLog).where(
            RiskAssessmentLog.id == decision_id,
            RiskAssessmentLog.kind == "diary",
            RiskAssessmentLog.user_id == user_id,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise ValueError("decision not found")
    db.commit()
