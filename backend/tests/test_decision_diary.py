from __future__ import annotations

from sqlalchemy import select

from app.models import Market, PricePoint, RiskAssessmentLog


def test_decision_create_list_and_matured_update(client, db_session) -> None:
    create_response = client.post(
        "/api/decisions",
        json={
            "market_code": "ERCOT_NORTH",
            "position_gbp": 10000,
            "direction": "long",
            "horizon_hours": 1,
            "risk_gbp": 500,
            "likely_gbp": 50,
            "upside_gbp": 900,
            "thesis_text": "Wind lull should lift the next settlement window.",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["thesis_text"].startswith("Wind lull")
    assert created["realized_pnl_gbp"] is None

    list_response = client.get("/api/decisions")
    assert list_response.status_code == 200
    assert any(item["id"] == created["id"] for item in list_response.json())

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
    row = db_session.get(RiskAssessmentLog, created["id"])
    assert row is not None
    row.timestamp = prices[0].timestamp
    db_session.commit()

    matured_response = client.get(f"/api/decisions?market_id={market.id}")

    assert matured_response.status_code == 200
    matured = next(item for item in matured_response.json() if item["id"] == created["id"])
    assert matured["realized_pnl_gbp"] is not None
    assert matured["predicted_percentile"] is not None
