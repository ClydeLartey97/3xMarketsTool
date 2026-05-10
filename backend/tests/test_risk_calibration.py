from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Market, PricePoint, RiskAssessmentLog
from app.services.risk_calibration import fill_matured_risk_assessment_logs, risk_calibration_for_market


def _insert_logs(db_session, market_id: int, breaches: int, total: int = 1_000) -> None:
    now = datetime.now(timezone.utc)
    rows = []
    for index in range(total):
        breached = index < breaches
        rows.append(
            RiskAssessmentLog(
                timestamp=now - timedelta(hours=index % 240),
                market_id=market_id,
                position_gbp=10_000,
                direction="long",
                horizon_hours=24,
                risk_gbp=100,
                likely_gbp=10,
                upside_gbp=150,
                realized_pnl_gbp=-120 if breached else -20,
            )
        )
    db_session.add_all(rows)
    db_session.commit()


def test_risk_calibration_marks_understating_for_high_breach_rate(db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "GB_POWER"))
    assert market is not None
    _insert_logs(db_session, market.id, breaches=83)

    result = risk_calibration_for_market(db_session, market.id)

    assert result["sample_count"] == 1_000
    assert result["actual_breach_rate"] == 0.083
    assert result["calibration_status"] == "understating"


def test_risk_calibration_marks_honest_for_target_breach_rate(db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "GB_POWER"))
    assert market is not None
    _insert_logs(db_session, market.id, breaches=47)

    result = risk_calibration_for_market(db_session, market.id)

    assert result["sample_count"] == 1_000
    assert result["actual_breach_rate"] == 0.047
    assert result["calibration_status"] == "honest"


def test_risk_calibration_endpoint_returns_badge_payload(client, db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "GB_POWER"))
    assert market is not None
    _insert_logs(db_session, market.id, breaches=83)

    response = client.get(f"/api/markets/{market.id}/risk-calibration")

    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 1_000
    assert body["actual_breach_rate"] == 0.083
    assert body["calibration_status"] == "understating"


def test_fill_matured_risk_assessment_logs_sets_realized_pnl(db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    prices = list(
        db_session.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id)
            .order_by(PricePoint.timestamp.asc())
            .limit(3)
        ).all()
    )
    assert len(prices) >= 2
    row = RiskAssessmentLog(
        timestamp=prices[0].timestamp,
        market_id=market.id,
        position_gbp=10_000,
        direction="long",
        horizon_hours=1,
        risk_gbp=500,
        likely_gbp=50,
        upside_gbp=800,
    )
    db_session.add(row)
    db_session.commit()

    updated = fill_matured_risk_assessment_logs(db_session, now=prices[2].timestamp)

    db_session.refresh(row)
    assert updated == 1
    assert row.realized_pnl_gbp is not None
