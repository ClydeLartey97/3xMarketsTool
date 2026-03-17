from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Forecast


def list_alerts(db: Session, market_id: int, hours: int = 72) -> list[Alert]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Alert)
        .where(Alert.market_id == market_id, Alert.created_at >= since)
        .order_by(desc(Alert.created_at))
    )
    return list(db.scalars(stmt).all())


def refresh_alerts_for_market(db: Session, market_id: int) -> list[Alert]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    forecasts = list(
        db.scalars(
            select(Forecast)
            .where(Forecast.market_id == market_id)
            .order_by(Forecast.forecast_for_timestamp.desc())
            .limit(24)
        ).all()
    )
    events = list(
        db.scalars(
            select(Event).where(Event.market_id == market_id).order_by(Event.created_at.desc()).limit(5)
        ).all()
    )
    existing_titles = set(
        db.scalars(
            select(Alert.title).where(Alert.market_id == market_id, Alert.created_at >= since)
        ).all()
    )

    generated: list[Alert] = []
    if any(f.spike_probability >= 0.35 for f in forecasts):
        generated.append(
            Alert(
                market_id=market_id,
                alert_type="spike_risk",
                title="Spike risk above threshold",
                body="Forecast spike probability exceeded 35% for at least one upcoming hourly interval.",
                severity="high",
            )
        )

    if any(event.severity == "high" for event in events):
        generated.append(
            Alert(
                market_id=market_id,
                alert_type="major_event",
                title="High-severity structured event active",
                body="A recent event with high severity is likely influencing local price formation.",
                severity="medium",
            )
        )

    for alert in generated:
        if alert.title not in existing_titles:
            db.add(alert)
    db.commit()
    return generated
