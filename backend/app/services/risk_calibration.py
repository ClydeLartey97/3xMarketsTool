from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Market, PricePoint, RiskAssessmentLog

CLAIMED_BREACH_RATE = 0.05


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _kupiec_pof_p_value(breaches: int, sample_count: int, claimed_rate: float = CLAIMED_BREACH_RATE) -> float:
    if sample_count <= 0:
        return 1.0
    if breaches <= 0:
        lr_uc = -2.0 * (sample_count * math.log(max(1e-12, 1.0 - claimed_rate)))
        return float(math.erfc(math.sqrt(max(0.0, lr_uc) / 2.0)))
    if breaches >= sample_count:
        lr_uc = -2.0 * (sample_count * math.log(max(1e-12, claimed_rate)))
        return float(math.erfc(math.sqrt(max(0.0, lr_uc) / 2.0)))

    observed = breaches / sample_count
    log_null = (
        (sample_count - breaches) * math.log(max(1e-12, 1.0 - claimed_rate))
        + breaches * math.log(max(1e-12, claimed_rate))
    )
    log_alt = (
        (sample_count - breaches) * math.log(max(1e-12, 1.0 - observed))
        + breaches * math.log(max(1e-12, observed))
    )
    lr_uc = -2.0 * (log_null - log_alt)
    return float(math.erfc(math.sqrt(max(0.0, lr_uc) / 2.0)))


def log_risk_assessment(db: Session, result: dict[str, Any], user_id: int | None = None) -> RiskAssessmentLog | None:
    market = db.scalar(select(Market).where(Market.code == result["market_code"]))
    if not market:
        return None
    row = RiskAssessmentLog(
        timestamp=_as_utc(result.get("as_of") or datetime.now(timezone.utc)),
        market_id=market.id,
        user_id=user_id,
        position_gbp=float(result["position_gbp"]),
        direction=str(result["direction"]),
        horizon_hours=int(result["horizon_hours"]),
        risk_gbp=float(result["risk_gbp"]),
        likely_gbp=float(result["likely_gbp"]),
        upside_gbp=float(result["upside_gbp"]),
        realized_pnl_gbp=None,
        kind="auto",
        thesis_text=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _price_at_or_before(db: Session, market_id: int, timestamp: datetime) -> PricePoint | None:
    return db.scalar(
        select(PricePoint)
        .where(PricePoint.market_id == market_id, PricePoint.timestamp <= timestamp)
        .order_by(PricePoint.timestamp.desc())
        .limit(1)
    )


def _price_at_or_after(db: Session, market_id: int, timestamp: datetime) -> PricePoint | None:
    return db.scalar(
        select(PricePoint)
        .where(PricePoint.market_id == market_id, PricePoint.timestamp >= timestamp)
        .order_by(PricePoint.timestamp.asc())
        .limit(1)
    )


def fill_matured_risk_assessment_logs(
    db: Session,
    now: datetime | None = None,
    *,
    kind: str | None = None,
    user_id: int | None = None,
    market_id: int | None = None,
    limit: int = 500,
) -> int:
    now_utc = _as_utc(now or datetime.now(timezone.utc))
    stmt = (
        select(RiskAssessmentLog)
        .where(RiskAssessmentLog.realized_pnl_gbp.is_(None))
        .order_by(RiskAssessmentLog.timestamp.asc())
        .limit(max(1, int(limit)))
    )
    if kind is not None:
        stmt = stmt.where(RiskAssessmentLog.kind == kind)
    if user_id is not None:
        stmt = stmt.where(RiskAssessmentLog.user_id == user_id)
    if market_id is not None:
        stmt = stmt.where(RiskAssessmentLog.market_id == market_id)
    rows = list(
        db.scalars(stmt).all()
    )
    updated = 0
    for row in rows:
        maturity = _as_utc(row.timestamp) + timedelta(hours=row.horizon_hours)
        if maturity > now_utc:
            continue
        start_price = _price_at_or_before(db, row.market_id, _as_utc(row.timestamp))
        end_price = _price_at_or_after(db, row.market_id, maturity)
        if not start_price or not end_price or start_price.price_value == 0:
            continue
        direction_sign = 1.0 if row.direction == "long" else -1.0
        realized = direction_sign * row.position_gbp * (end_price.price_value - start_price.price_value) / abs(start_price.price_value)
        row.realized_pnl_gbp = round(float(realized), 2)
        updated += 1
    if updated:
        db.commit()
    return updated


def risk_calibration_for_market(
    db: Session,
    market_id: int,
    *,
    now: datetime | None = None,
    lookback_days: int = 30,
) -> dict[str, Any]:
    now_utc = _as_utc(now or datetime.now(timezone.utc))
    since = now_utc - timedelta(days=lookback_days)
    rows = list(
        db.scalars(
            select(RiskAssessmentLog)
            .where(
                RiskAssessmentLog.market_id == market_id,
                RiskAssessmentLog.realized_pnl_gbp.is_not(None),
                RiskAssessmentLog.timestamp >= since,
            )
        ).all()
    )
    sample_count = len(rows)
    breaches = sum(1 for row in rows if float(row.realized_pnl_gbp or 0.0) <= -float(row.risk_gbp))
    actual_rate = breaches / sample_count if sample_count else 0.0
    p_value = _kupiec_pof_p_value(breaches, sample_count)
    if sample_count == 0 or p_value >= 0.05:
        status = "honest"
    elif actual_rate > CLAIMED_BREACH_RATE:
        status = "understating"
    else:
        status = "overstating"
    return {
        "market_id": market_id,
        "claimed_breach_rate": CLAIMED_BREACH_RATE,
        "actual_breach_rate": round(float(actual_rate), 4),
        "kupiec_p_value": round(float(p_value), 6),
        "sample_count": sample_count,
        "calibration_status": status,
    }
