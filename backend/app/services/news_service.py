from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.news_sources import NEWS_SOURCES, NEWS_SOURCE_MAP
from app.models import Event, Market, NewsArticle
from app.schemas.domain import NewsArticleRead, NewsSourceRead


def list_news_sources() -> list[NewsSourceRead]:
    return [NewsSourceRead(**source) for source in NEWS_SOURCES]


def list_news_articles(db: Session, market_id: int | None = None, hours: int = 168, limit: int = 20) -> list[NewsArticleRead]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(NewsArticle).where(NewsArticle.published_at >= since).order_by(desc(NewsArticle.published_at)).limit(limit)
    articles = list(db.scalars(stmt).all())
    if not articles:
        return []

    events_by_article = {
        event.article_id: event
        for event in db.scalars(select(Event).where(Event.article_id.in_([article.id for article in articles])))
    }
    markets = list(db.scalars(select(Market)))
    markets_by_id = {market.id: market for market in markets}
    markets_by_code = {market.code: market for market in markets}
    selected_market = markets_by_id.get(market_id) if market_id is not None else None

    results: list[NewsArticleRead] = []
    for article in articles:
        event = events_by_article.get(article.id)
        raw = article.raw_json or {}
        raw_market = markets_by_code.get(raw.get("market_code")) if raw.get("market_code") else None
        if market_id is not None and event and event.market_id != market_id:
            continue
        if market_id is not None and not event and (not selected_market or raw.get("market_code") != selected_market.code):
            continue

        source_key = raw.get("source_key")
        source_meta = NEWS_SOURCE_MAP.get(source_key)
        display_title = raw.get("translated_title") or article.title
        display_summary = raw.get("translated_summary") or raw.get("summary") or article.body[:220]
        market = markets_by_id.get(event.market_id) if event and event.market_id else raw_market

        results.append(
            NewsArticleRead(
                id=article.id,
                market_id=event.market_id if event else None,
                market_code=market.code if market else raw.get("market_code"),
                title=article.title,
                display_title=display_title,
                summary=raw.get("summary") or article.body[:220],
                display_summary=display_summary,
                source_name=article.source_name,
                source_url=article.source_url,
                source_language=raw.get("original_language") or (source_meta["language"] if source_meta else "en"),
                is_auto_translated=bool(raw.get("translated_title") or raw.get("translated_summary")),
                credibility_rating=float(raw.get("credibility_rating") or (source_meta["credibility_rating"] if source_meta else 82)),
                credibility_label=raw.get("credibility_label") or (source_meta["credibility_label"] if source_meta else "Curated"),
                published_at=article.published_at,
                event_type=event.event_type if event else None,
                price_direction=event.price_direction if event else None,
                affected_region=event.affected_region if event else market.region if market else None,
            )
        )

    return results
