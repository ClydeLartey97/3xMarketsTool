from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.events.extractor import extract_primary_event
from app.events.impact import estimate_price_impact_pct
from app.models import Event, Market, NewsArticle
from app.schemas.domain import ArticleIngestRequest
from app.services.market_service import get_market_by_code


SEVERITY_SCORE = {"low": 1.0, "medium": 2.0, "high": 3.0}


def list_events(db: Session, market_id: int | None = None, hours: int = 72) -> list[Event]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(Event).where(Event.created_at >= since).order_by(desc(Event.created_at))
    if market_id is not None:
        stmt = stmt.where(Event.market_id == market_id)
    return list(db.scalars(stmt).all())


def ingest_article(db: Session, payload: ArticleIngestRequest) -> Event | None:
    market = get_market_by_code(db, payload.market_code) if payload.market_code else None
    article = NewsArticle(
        title=payload.title,
        body=payload.body,
        source_name=payload.source_name,
        source_url=payload.source_url,
        published_at=payload.published_at,
        raw_json=payload.model_dump(mode="json"),
        processed_status="processed",
    )
    db.add(article)
    db.flush()

    extracted = extract_primary_event(payload.title, payload.body, market.region if market else "ERCOT")
    if not extracted:
        article.processed_status = "irrelevant"
        db.commit()
        return None

    event = Event(
        article_id=article.id,
        market_id=market.id if market else None,
        event_type=extracted.event_type,
        title=extracted.title,
        description=extracted.description,
        affected_region=extracted.affected_region,
        asset_type=extracted.asset_type,
        capacity_impact_mw=extracted.capacity_impact_mw,
        start_time=extracted.start_time,
        expected_end_time=extracted.expected_end_time,
        severity=extracted.severity,
        confidence=extracted.confidence,
        price_direction=extracted.price_direction,
        estimated_price_impact_pct=estimate_price_impact_pct(extracted),
        rationale=extracted.rationale,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def events_as_feature_frame(events: list[Event]) -> list[dict]:
    feature_rows = []
    for event in events:
        feature_rows.append(
            {
                "timestamp": event.start_time or event.created_at,
                "severity_score": SEVERITY_SCORE.get(event.severity, 1.0),
                "impact_pct": event.estimated_price_impact_pct or 0.0,
            }
        )
    return feature_rows
