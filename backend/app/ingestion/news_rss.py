"""RSS news fetcher for 3x power market platform.

Pulls from public RSS feeds of high-credibility energy news sources,
extracts market-relevant events, and inserts into the database.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

logger = logging.getLogger(__name__)

ENERGY_RSS_FEEDS = [
    {
        "key": "eia_today",
        "url": "https://www.eia.gov/rss/todayinenergy.xml",
        "name": "EIA Today in Energy",
        "credibility": 96,
        "label": "Official — US EIA",
    },
    {
        "key": "utility_dive",
        "url": "https://www.utilitydive.com/feeds/news/",
        "name": "Utility Dive",
        "credibility": 88,
        "label": "Tier 2 specialist",
    },
    {
        "key": "power_mag",
        "url": "https://www.powermag.com/feed/",
        "name": "POWER Magazine",
        "credibility": 88,
        "label": "Tier 2 specialist",
    },
    {
        "key": "canary_media",
        "url": "https://www.canarymedia.com/feed.rss",
        "name": "Canary Media",
        "credibility": 86,
        "label": "Tier 2 specialist",
    },
    {
        "key": "nrel_news",
        "url": "https://www.nrel.gov/rss/news.xml",
        "name": "NREL News",
        "credibility": 94,
        "label": "Official — US national lab",
    },
    {
        "key": "renewableenergyworld",
        "url": "https://www.renewableenergyworld.com/feed/",
        "name": "Renewable Energy World",
        "credibility": 84,
        "label": "Tier 2 specialist",
    },
]

_STRIP_TAGS = re.compile(r"<[^>]+>")
_NON_WORDS = re.compile(r"[^a-z0-9]+")

MARKET_ALIASES: dict[str, tuple[str, ...]] = {
    "ERCOT_NORTH": (
        "ercot north",
        "north hub",
        "hb north",
        "texas grid",
        "texas power",
        "ercot",
    ),
    "ERCOT_HOUSTON": (
        "ercot houston",
        "houston hub",
        "hb houston",
        "houston",
    ),
    "PJM_WESTERN_HUB": (
        "pjm western hub",
        "pjm western",
        "pjm west",
        "pjm",
        "mid atlantic",
        "pennsylvania jersey maryland",
    ),
    "NYISO_ZONE_J": (
        "nyiso zone j",
        "zone j",
        "new york city",
        "new york power",
        "nyiso",
        "nyc",
    ),
    "ISONE_MASS_HUB": (
        "iso ne mass hub",
        "iso new england",
        "isone mass hub",
        "mass hub",
        "new england power",
        "massachusetts power",
        "iso ne",
        "isone",
    ),
    "GB_POWER": (
        "great britain power",
        "british power",
        "uk power",
        "united kingdom power",
        "national grid eso",
        "national energy system operator",
        "neso",
        "ofgem",
        "britain",
        "gb power",
    ),
    "EPEX_DE": (
        "epex germany",
        "epex de",
        "epex de lu",
        "german power",
        "germany power",
        "german day ahead",
        "germany day ahead",
        "de lu",
    ),
    "EPEX_FR": (
        "epex france",
        "epex fr",
        "french power",
        "france power",
        "french day ahead",
        "france day ahead",
        "rte france",
        "rte",
    ),
    "NORDPOOL_SE3": (
        "nord pool se3",
        "nordpool se3",
        "se3",
        "sweden se3",
        "swedish power",
        "nordic power",
        "nord pool",
        "nordpool",
        "nordics",
    ),
}


def _strip_html(text: str) -> str:
    return _STRIP_TAGS.sub("", text or "").strip()


def _normalise_text(text: str) -> str:
    lowered = (text or "").lower().replace("&", " and ")
    return " " + _NON_WORDS.sub(" ", lowered).strip() + " "


def _normalise_alias(text: str) -> str:
    return _normalise_text(text).strip()


def _market_aliases(market: Any) -> tuple[str, ...]:
    metadata = getattr(market, "metadata_json", None) or {}
    aliases = {
        str(getattr(market, "name", "")),
        str(getattr(market, "region", "")),
        str(getattr(market, "code", "")),
        str(getattr(market, "code", "")).replace("_", " "),
    }
    aliases.update(MARKET_ALIASES.get(str(getattr(market, "code", "")), ()))
    if metadata.get("market_family"):
        aliases.add(str(metadata["market_family"]))
    for node in metadata.get("nodes") or []:
        aliases.add(str(node).replace("_", " "))

    normalised = {
        _normalise_alias(alias)
        for alias in aliases
        if alias and len(_normalise_alias(alias)) >= 2
    }
    return tuple(sorted(normalised, key=len, reverse=True))


def _match_market_for_article(
    market_aliases: dict[str, tuple[Any, tuple[str, ...]]],
    title: str,
    body: str,
) -> Any | None:
    haystack = _normalise_text(f"{title} {body}")
    best_market = None
    best_score = 0
    best_specificity = 0
    for _code, (market, aliases) in market_aliases.items():
        score = 0
        specificity = 0
        for alias in aliases:
            if f" {alias} " not in haystack:
                continue
            alias_words = alias.count(" ") + 1
            weight = 1 + min(4, len(alias) // 8) + max(0, alias_words - 1)
            score += weight
            specificity = max(specificity, len(alias))
        if score > best_score or (score == best_score and specificity > best_specificity):
            best_market = market
            best_score = score
            best_specificity = specificity
    return best_market if best_score > 0 else None


def _parse_entry_time(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _fetch_feed(feed: dict, max_articles: int = 8) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = client.get(
                feed["url"],
                headers={"User-Agent": "3x-market-intelligence/1.0 (energy research)"},
            )
            resp.raise_for_status()
            content = resp.text
    except Exception as exc:
        logger.warning("RSS fetch error (%s): %s", feed["name"], exc)
        return []

    try:
        parsed = feedparser.parse(content)
    except Exception as exc:
        logger.warning("RSS parse error (%s): %s", feed["name"], exc)
        return []

    articles = []
    for entry in parsed.entries[:max_articles]:
        published = _parse_entry_time(entry)
        if not published or published < cutoff:
            continue

        title = _strip_html(getattr(entry, "title", ""))[:256]
        link = getattr(entry, "link", feed["url"])[:512]

        # Build summary from description/summary/content
        summary_raw = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
        )
        # feedparser may give content list
        if not summary_raw and hasattr(entry, "content"):
            for c in entry.content:
                summary_raw = c.get("value", "")
                if summary_raw:
                    break

        summary = _strip_html(summary_raw)[:500]
        short_summary = summary[:220]

        if not title:
            continue

        articles.append({
            "title": title,
            "body": summary,
            "source_name": feed["name"],
            "source_url": link,
            "published_at": published,
            "raw_json": {
                "source_key": feed["key"],
                "credibility_rating": feed["credibility"],
                "credibility_label": feed["label"],
                "summary": short_summary,
            },
        })

    logger.info("RSS (%s): parsed %d articles", feed["name"], len(articles))
    return articles


def ingest_rss_feeds(db: Any, max_per_feed: int = 6) -> int:
    """Fetch all configured RSS feeds, ingest new articles, extract events."""
    from app.events.extractor import extract_primary_event
    from app.events.impact import estimate_price_impact_pct
    from app.models import Event, Market, NewsArticle
    from sqlalchemy import select

    # Build existing URL set to avoid duplicates
    existing_urls: set[str] = set(
        r[0] for r in db.execute(select(NewsArticle.source_url)).all()
    )

    # Load markets for event-market matching
    markets = list(db.scalars(select(Market)).all())
    market_keywords: dict[str, Any] = {}
    for m in markets:
        market_keywords[m.code] = (m, _market_aliases(m))

    total_inserted = 0

    for feed in ENERGY_RSS_FEEDS:
        raw_articles = _fetch_feed(feed, max_articles=max_per_feed)

        for art in raw_articles:
            if art["source_url"] in existing_urls:
                continue
            matched_market = _match_market_for_article(market_keywords, art["title"], art["body"])
            raw_json = dict(art["raw_json"])
            if matched_market:
                raw_json["market_code"] = matched_market.code

            article = NewsArticle(
                title=art["title"],
                body=art["body"],
                source_name=art["source_name"],
                source_url=art["source_url"],
                published_at=art["published_at"],
                raw_json=raw_json,
                processed_status="pending",
            )
            db.add(article)
            db.flush()
            existing_urls.add(art["source_url"])

            # Try to extract a structured market event
            extracted = extract_primary_event(art["title"], art["body"])
            if extracted:
                impact_pct = estimate_price_impact_pct(extracted)
                from app.services.event_analogues import populate_event_analogues

                event = Event(
                    article_id=article.id,
                    market_id=matched_market.id if matched_market else None,
                    event_type=extracted.event_type,
                    title=extracted.title,
                    description=extracted.description,
                    affected_region=extracted.affected_region,
                    asset_type=extracted.asset_type,
                    capacity_impact_mw=extracted.capacity_impact_mw,
                    zone=extracted.zone,
                    node=extracted.node,
                    magnitude_mw=extracted.magnitude_mw,
                    duration_hours_estimate=extracted.duration_hours_estimate,
                    duration_hours_p10=extracted.duration_hours_p10,
                    duration_hours_p90=extracted.duration_hours_p90,
                    analogue_event_ids=extracted.analogue_event_ids or [],
                    classifier_version=extracted.classifier_version,
                    start_time=extracted.start_time,
                    expected_end_time=extracted.expected_end_time,
                    severity=extracted.severity,
                    confidence=extracted.confidence,
                    price_direction=extracted.price_direction,
                    estimated_price_impact_pct=impact_pct,
                    rationale=extracted.rationale,
                )
                db.add(event)
                db.flush()
                populate_event_analogues(event, db)
                article.processed_status = "processed"
            else:
                article.processed_status = "no_event"

            db.flush()
            total_inserted += 1

    db.commit()
    logger.info("RSS ingest complete: %d new articles", total_inserted)
    return total_inserted
