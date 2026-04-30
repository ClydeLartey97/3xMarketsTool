from __future__ import annotations

from sqlalchemy import select

from app.models import Market, PricePoint


def test_market_history_filters_by_date_range(client, db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    points = list(db_session.scalars(
        select(PricePoint)
        .where(PricePoint.market_id == market.id)
        .order_by(PricePoint.timestamp.asc())
        .limit(12)
    ).all())
    assert len(points) >= 8

    start = points[2].timestamp
    end = points[6].timestamp
    response = client.get(
        f"/api/markets/{market.id}/history",
        params={"from": start.isoformat(), "to": end.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert body[0]["timestamp"].startswith(start.isoformat()[:19])
    assert body[-1]["timestamp"].startswith(end.isoformat()[:19])


def test_market_history_rejects_reversed_range(client, db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None

    response = client.get(
        f"/api/markets/{market.id}/history",
        params={"from": "2026-01-02T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 400


def test_dashboard_history_hours_parameter_controls_recent_prices(client) -> None:
    response = client.get("/api/dashboard/ERCOT_NORTH", params={"history_hours": 24})

    assert response.status_code == 200
    body = response.json()
    assert 0 < len(body["recent_prices"]) <= 24
