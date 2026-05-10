"""Build a silver-labelled news corpus for the domain scorer.

The script tries public source collectors first, then fills any shortfall with
deterministic market-event templates that mirror the same source families. Each
row is labelled by the current in-repo event extractor and news scorer, so the
output is useful for bootstrapping D.2 without requiring a live Gemini key.

Usage:
    PYTHONPATH=. python3 scripts/build_news_dataset.py
    PYTHONPATH=. python3 scripts/build_news_dataset.py --no-network --target-rows 5000
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import feedparser
import httpx

from app.events.extractor import ExtractedEvent, extract_primary_event
from app.ingestion.news_rss import ENERGY_RSS_FEEDS
from app.services.llm_scorer import ScoredArticle, _score_heuristic


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "news_train.jsonl"
USER_AGENT = "3x-market-intelligence/1.0 (news-corpus-builder)"


@dataclass(frozen=True)
class SourceArticle:
    title: str
    body: str
    source_name: str
    source_family: str
    source_url: str
    published_at: datetime
    credibility: float
    market_code: str
    source_kind: str

    @property
    def text(self) -> str:
        return f"{self.title}\n\n{self.body}".strip()


MARKETS = [
    {"code": "ERCOT_NORTH", "region": "ERCOT North", "node": "North Hub"},
    {"code": "PJM_WESTERN_HUB", "region": "PJM Western Hub", "node": "Western Hub"},
    {"code": "GB_POWER", "region": "Great Britain", "node": "N2EX"},
    {"code": "EPEX_DE", "region": "Germany", "node": "EPEX DE"},
    {"code": "EPEX_FR", "region": "France", "node": "EPEX FR"},
    {"code": "NORDPOOL_SE3", "region": "Sweden SE3", "node": "SE3"},
]

SOURCE_FAMILIES = [
    {
        "family": "ferc_elibrary",
        "name": "FERC eLibrary",
        "url": "https://elibrary.ferc.gov/eLibrary/search",
        "credibility": 99,
    },
    {
        "family": "entsoe_unavailability",
        "name": "ENTSO-E Transparency Platform",
        "url": "https://transparency.entsoe.eu/",
        "credibility": 98,
    },
    {
        "family": "elexon_boa",
        "name": "ELEXON BOA",
        "url": "https://data.elexon.co.uk/bmrs/api/v1/datasets/BOALF",
        "credibility": 99,
    },
    {
        "family": "reuters_public_rss",
        "name": "Reuters Energy",
        "url": "https://www.reutersagency.com/feed/?best-topics=energy&post_type=best",
        "credibility": 98,
    },
    {
        "family": "argus_public_rss",
        "name": "Argus Media Power",
        "url": "https://www.argusmedia.com/en/news-and-insights/rss",
        "credibility": 93,
    },
]

BOOTSTRAP_TEMPLATES = [
    {
        "event_type": "generator_outage",
        "title": "{region} generator outage removes {capacity} MW from the prompt stack",
        "body": (
            "{source} reported a generator outage at {node}, with {capacity} MW offline for roughly "
            "{duration} hours during the evening ramp. Traders said the forced outage tightens reserve "
            "margins and lifts scarcity risk for the next delivery window."
        ),
    },
    {
        "event_type": "transmission_outage",
        "title": "{region} transmission outage creates a constraint near {node}",
        "body": (
            "{source} described a transmission outage and line outage limiting transfer capability into "
            "{node}. The constraint affects about {capacity} MW of flow and raises local congestion risk "
            "until crews return the asset to service."
        ),
    },
    {
        "event_type": "extreme_weather_alert",
        "title": "{region} extreme heat weather alert raises peak demand risk",
        "body": (
            "{source} said an extreme heat advisory is expected to push peak demand higher for {duration} "
            "hours. Operators are watching reserve margins as cooling load builds across {region}."
        ),
    },
    {
        "event_type": "renewable_forecast_revision",
        "title": "{region} wind forecast revised lower ahead of the evening ramp",
        "body": (
            "{source} said the wind forecast revised lower by {capacity} MW, while solar output fades into "
            "the evening peak. The renewable forecast revision could lift balancing prices in {region}."
        ),
    },
    {
        "event_type": "demand_shock",
        "title": "{region} data center load growth adds a fresh demand shock",
        "body": (
            "{source} highlighted demand growth from large load interconnections near {node}. The new data "
            "center demand shock is expected to add {capacity} MW of peak exposure over the planning window."
        ),
    },
    {
        "event_type": "regulatory_policy_announcement",
        "title": "{region} market rule change filing lands in the regulatory docket",
        "body": (
            "{source} published a regulatory filing and policy announcement on market rule change details "
            "for {region}. The consultation could alter price collars, queue timing, and short-term liquidity."
        ),
    },
]


def collect_public_rss(max_per_feed: int = 60) -> list[SourceArticle]:
    feed_defs = [
        *ENERGY_RSS_FEEDS,
        {
            "key": "reuters_energy_public",
            "url": SOURCE_FAMILIES[3]["url"],
            "name": SOURCE_FAMILIES[3]["name"],
            "credibility": SOURCE_FAMILIES[3]["credibility"],
        },
        {
            "key": "argus_power_public",
            "url": SOURCE_FAMILIES[4]["url"],
            "name": SOURCE_FAMILIES[4]["name"],
            "credibility": SOURCE_FAMILIES[4]["credibility"],
        },
    ]
    rows: list[SourceArticle] = []
    for feed in feed_defs:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.get(str(feed["url"]), headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
            parsed = feedparser.parse(response.text)
        except Exception:
            continue

        for entry in parsed.entries[:max_per_feed]:
            title = _strip_html(str(getattr(entry, "title", "")))[:300]
            body = _strip_html(
                str(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            )[:1400]
            if not title:
                continue
            rows.append(
                SourceArticle(
                    title=title,
                    body=body or title,
                    source_name=str(feed["name"]),
                    source_family=str(feed["key"]),
                    source_url=str(getattr(entry, "link", feed["url"])),
                    published_at=_entry_time(entry),
                    credibility=float(feed["credibility"]),
                    market_code=_guess_market_code(f"{title} {body}"),
                    source_kind="public_rss",
                )
            )
    return rows


def collect_elexon_boa(days: int = 7, max_rows: int = 500) -> list[SourceArticle]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "publishDateTimeFrom": start.isoformat().replace("+00:00", "Z"),
        "publishDateTimeTo": end.isoformat().replace("+00:00", "Z"),
        "format": "json",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(SOURCE_FAMILIES[2]["url"], params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    raw_rows = payload.get("data", payload if isinstance(payload, list) else [])
    rows: list[SourceArticle] = []
    for index, item in enumerate(raw_rows[:max_rows]):
        unit = str(item.get("bmUnitId") or item.get("nationalGridBmUnit") or item.get("unit") or "GB unit")
        level = _first_number(item, ("bidOfferAcceptanceLevel", "levelFrom", "levelTo", "volume"))
        price = _first_number(item, ("acceptancePrice", "price", "bidOfferAcceptancePrice"))
        title = f"ELEXON BOA acceptance changes {unit} dispatch by {abs(level or 0):.0f} MW"
        body = (
            f"ELEXON BOA data show bid offer acceptance activity for {unit}. Dispatch changed by "
            f"{abs(level or 0):.0f} MW with an indicated price near {price or 0:.2f}, a balancing action "
            "that can signal short-term scarcity, constraints, or renewable forecast revision risk."
        )
        rows.append(
            SourceArticle(
                title=title,
                body=body,
                source_name="ELEXON BOA",
                source_family="elexon_boa",
                source_url=f"{SOURCE_FAMILIES[2]['url']}#row-{index}",
                published_at=end,
                credibility=99.0,
                market_code="GB_POWER",
                source_kind="elexon_api",
            )
        )
    return rows


def collect_entsoe_unavailability(days: int = 7, max_rows: int = 500) -> list[SourceArticle]:
    token = os.environ.get("ENTSOE_API_TOKEN") or os.environ.get("ENTSOE_SECURITY_TOKEN")
    if not token:
        return []
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "securityToken": token,
        "documentType": "A78",
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get("https://web-api.tp.entsoe.eu/api", params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except Exception:
        return []

    rows: list[SourceArticle] = []
    for index, element in enumerate(root.iter()):
        if len(rows) >= max_rows:
            break
        text = " ".join(part.strip() for part in element.itertext() if part.strip())
        if "unavailability" not in text.lower() and "outage" not in text.lower():
            continue
        capacity = _capacity_from_text(text) or 500.0
        rows.append(
            SourceArticle(
                title=f"ENTSO-E unavailability message flags {capacity:.0f} MW of generation risk",
                body=f"ENTSO-E Transparency Platform unavailability message: {text[:1200]}",
                source_name="ENTSO-E Transparency Platform",
                source_family="entsoe_unavailability",
                source_url="https://web-api.tp.entsoe.eu/api",
                published_at=end,
                credibility=98.0,
                market_code="EPEX_DE",
                source_kind="entsoe_api",
            )
        )
    return rows


def collect_ferc_daily_filings(days: int = 7, max_rows: int = 500) -> list[SourceArticle]:
    """Best-effort FERC collector.

    FERC eLibrary does not expose a stable unauthenticated JSON API in this
    codebase, so the endpoint can be overridden with FERC_ELIBRARY_JSON_URL in
    environments that have an internal mirror. When unavailable, the builder
    falls back to FERC-shaped bootstrap rows.
    """
    url = os.environ.get("FERC_ELIBRARY_JSON_URL")
    if not url:
        return []
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT}, params={"days": days})
            response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    raw_rows = payload.get("data", payload if isinstance(payload, list) else [])
    rows: list[SourceArticle] = []
    for item in raw_rows[:max_rows]:
        title = str(item.get("title") or item.get("description") or "FERC eLibrary filing")[:300]
        docket = str(item.get("docket") or item.get("docketNumber") or "power market docket")
        body = str(item.get("summary") or item.get("body") or title)[:1400]
        rows.append(
            SourceArticle(
                title=title,
                body=f"FERC eLibrary filing {docket}: {body}",
                source_name="FERC eLibrary",
                source_family="ferc_elibrary",
                source_url=str(item.get("url") or SOURCE_FAMILIES[0]["url"]),
                published_at=datetime.now(timezone.utc),
                credibility=99.0,
                market_code=_guess_market_code(f"{title} {body}"),
                source_kind="ferc_elibrary",
            )
        )
    return rows


def generate_bootstrap_articles(target_rows: int, start_index: int = 0) -> list[SourceArticle]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[SourceArticle] = []
    for offset in range(max(0, target_rows)):
        index = start_index + offset
        market = MARKETS[index % len(MARKETS)]
        source = SOURCE_FAMILIES[(index // len(MARKETS)) % len(SOURCE_FAMILIES)]
        template = BOOTSTRAP_TEMPLATES[(index // (len(MARKETS) * len(SOURCE_FAMILIES))) % len(BOOTSTRAP_TEMPLATES)]
        capacity = 120 + ((index * 37) % 2400)
        if template["event_type"] in {"generator_outage", "transmission_outage"}:
            capacity = max(700, capacity)
        duration = 2 + (index % 22)
        values = {
            "region": market["region"],
            "node": market["node"],
            "capacity": capacity,
            "duration": duration,
            "source": source["name"],
        }
        rows.append(
            SourceArticle(
                title=str(template["title"]).format(**values),
                body=str(template["body"]).format(**values),
                source_name=str(source["name"]),
                source_family=str(source["family"]),
                source_url=f"{source['url']}#silver-{index}",
                published_at=now - timedelta(hours=index % (24 * 365)),
                credibility=float(source["credibility"]),
                market_code=str(market["code"]),
                source_kind="bootstrap_template",
            )
        )
    return rows


def build_records(
    articles: list[SourceArticle],
    *,
    target_rows: int = 5000,
    min_confidence: float = 0.55,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    candidates = list(articles)
    if len(candidates) < target_rows:
        candidates.extend(generate_bootstrap_articles(target_rows - len(candidates), start_index=len(candidates)))

    index = 0
    while len(records) < target_rows:
        if index >= len(candidates):
            candidates.extend(generate_bootstrap_articles(target_rows - len(records), start_index=index))
        article = candidates[index]
        index += 1
        digest = hashlib.sha1(article.text.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        record = label_article(article, record_id=digest, min_confidence=min_confidence)
        if record:
            records.append(record)
    return records


def label_article(
    article: SourceArticle,
    *,
    record_id: str | None = None,
    min_confidence: float = 0.55,
) -> dict[str, Any] | None:
    event = extract_primary_event(article.title, article.body, _market_region(article.market_code))
    events_summary = [_event_summary(event)] if event else []
    score = _score_heuristic(
        [
            ScoredArticle(
                title=article.title,
                summary=article.body,
                source=article.source_name,
                published_at=article.published_at,
                credibility=article.credibility,
            )
        ],
        events_summary,
    )
    label_confidence = max(float(score.get("confidence", 0.0)), event.confidence if event else 0.0)
    if label_confidence < min_confidence:
        return None
    label_dict = {
        "event_type": event.event_type if event else "no_event",
        "asset_type": event.asset_type if event else "none",
        "affected_region": event.affected_region if event else _market_region(article.market_code),
        "price_direction": event.price_direction if event else "neutral",
        "capacity_impact_mw": event.capacity_impact_mw if event else None,
        "duration_hours_estimate": _duration_hours(event),
        "severity": event.severity if event else "low",
        "event_confidence": round(event.confidence if event else 0.0, 3),
        "catalyst_severity": score["catalyst_severity"],
        "asymmetry": score["asymmetry"],
        "tail_multiplier": score["tail_multiplier"],
        "regime": score["regime"],
        "scorer_confidence": score["confidence"],
        "label_confidence": round(label_confidence, 3),
        "provider": score.get("provider", "heuristic"),
        "silver_label": True,
    }
    return {
        "id": record_id or hashlib.sha1(article.text.encode("utf-8")).hexdigest(),
        "text": article.text,
        "label_dict": label_dict,
        "metadata": {
            "source_name": article.source_name,
            "source_family": article.source_family,
            "source_kind": article.source_kind,
            "source_url": article.source_url,
            "published_at": article.published_at.isoformat(),
            "credibility": article.credibility,
            "market_code": article.market_code,
        },
    }


def collect_network_articles(max_per_source: int = 500) -> list[SourceArticle]:
    rows: list[SourceArticle] = []
    rows.extend(collect_public_rss(max_per_feed=min(80, max_per_source)))
    rows.extend(collect_ferc_daily_filings(max_rows=max_per_source))
    rows.extend(collect_entsoe_unavailability(max_rows=max_per_source))
    rows.extend(collect_elexon_boa(max_rows=max_per_source))
    return rows


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build silver-labelled news_train.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-rows", type=int, default=5000)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--max-per-source", type=int, default=500)
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()

    articles = [] if args.no_network else collect_network_articles(max_per_source=args.max_per_source)
    records = build_records(
        articles,
        target_rows=args.target_rows,
        min_confidence=args.min_confidence,
    )
    write_jsonl(records, args.output)
    source_counts: dict[str, int] = {}
    for record in records:
        source = str(record["metadata"]["source_family"])
        source_counts[source] = source_counts.get(source, 0) + 1
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(records),
                "network_candidates": len(articles),
                "source_counts": source_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def _entry_time(entry: Any) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _guess_market_code(text: str) -> str:
    lowered = text.lower()
    if "ercot" in lowered or "texas" in lowered:
        return "ERCOT_NORTH"
    if "pjm" in lowered or "ferc" in lowered:
        return "PJM_WESTERN_HUB"
    if "britain" in lowered or "uk" in lowered or "elexon" in lowered:
        return "GB_POWER"
    if "france" in lowered:
        return "EPEX_FR"
    if "nordic" in lowered or "sweden" in lowered:
        return "NORDPOOL_SE3"
    return "EPEX_DE" if "germany" in lowered or "entso" in lowered else "ERCOT_NORTH"


def _market_region(market_code: str) -> str:
    return next((item["region"] for item in MARKETS if item["code"] == market_code), "ERCOT")


def _event_summary(event: ExtractedEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "severity": event.severity,
        "affected_region": event.affected_region,
        "title": event.title,
    }


def _duration_hours(event: ExtractedEvent | None) -> float | None:
    if not event or not event.start_time or not event.expected_end_time:
        return None
    return round(max(0.0, (event.expected_end_time - event.start_time).total_seconds() / 3600), 2)


def _first_number(item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _capacity_from_text(text: str) -> float | None:
    match = re.search(r"(\d{2,5}(?:\.\d+)?)\s?MW", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


if __name__ == "__main__":
    main()
