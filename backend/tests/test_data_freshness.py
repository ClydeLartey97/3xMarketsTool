from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Market, PricePoint


def test_dashboard_surfaces_data_freshness_and_synthetic_share(client, db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    all_points = list(db_session.scalars(
        select(PricePoint)
        .where(PricePoint.market_id == market.id)
        .order_by(PricePoint.timestamp.desc())
    ).all())
    for idx, point in enumerate(all_points):
        point.timestamp = now - timedelta(days=3, hours=idx)

    points = list(db_session.scalars(
        select(PricePoint)
        .where(PricePoint.market_id == market.id)
        .order_by(PricePoint.timestamp.desc())
        .limit(24)
    ).all())
    assert len(points) == 24

    for idx, point in enumerate(points):
        point.timestamp = now - timedelta(hours=idx)
        point.source = "computed-fundamentals" if idx < 12 else "eia-ERCO"
    db_session.commit()

    response = client.get("/api/dashboard/ERCOT_NORTH", params={"history_hours": 48})

    assert response.status_code == 200
    metrics = response.json()["key_metrics"]
    assert "data_freshness_minutes" in metrics
    assert "synthetic_share_24h" in metrics
    assert metrics["data_freshness_minutes"] >= 0
    assert 0.45 <= metrics["synthetic_share_24h"] <= 0.55


def test_market_read_exposes_degraded_data_status(client, db_session) -> None:
    market = db_session.scalar(select(Market).where(Market.code == "ERCOT_NORTH"))
    assert market is not None
    metadata = dict(market.metadata_json or {})
    metadata["data_status"] = "degraded"
    market.metadata_json = metadata
    db_session.commit()

    response = client.get(f"/api/markets/{market.id}")

    assert response.status_code == 200
    assert response.json()["data_status"] == "degraded"
