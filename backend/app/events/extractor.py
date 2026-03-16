from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re


@dataclass
class ExtractedEvent:
    event_type: str
    title: str
    description: str
    affected_region: str
    asset_type: str
    capacity_impact_mw: float | None
    start_time: datetime | None
    expected_end_time: datetime | None
    severity: str
    confidence: float
    price_direction: str
    rationale: str


EVENT_PATTERNS: dict[str, dict[str, object]] = {
    "generator_outage": {
        "keywords": ["generator outage", "unit trip", "forced outage", "offline"],
        "asset_type": "generation",
        "price_direction": "bullish",
    },
    "transmission_outage": {
        "keywords": ["transmission outage", "line outage", "constraint", "interconnector issue"],
        "asset_type": "transmission",
        "price_direction": "bullish",
    },
    "extreme_weather_alert": {
        "keywords": ["extreme heat", "heat advisory", "cold snap", "winter storm", "weather alert"],
        "asset_type": "weather",
        "price_direction": "bullish",
    },
    "renewable_forecast_revision": {
        "keywords": ["wind forecast revised lower", "solar forecast revised lower", "renewable forecast revision"],
        "asset_type": "renewables",
        "price_direction": "bullish",
    },
    "regulatory_policy_announcement": {
        "keywords": ["regulatory filing", "market rule change", "policy announcement", "commission approved"],
        "asset_type": "policy",
        "price_direction": "uncertain",
    },
}

REGION_MAP = {
    "ercot": "ERCOT",
    "north hub": "ERCOT North",
    "houston": "ERCOT Houston",
    "west zone": "ERCOT West",
}


def extract_primary_event(title: str, body: str, market_region: str = "ERCOT") -> ExtractedEvent | None:
    haystack = f"{title} {body}".lower()

    matched_type = None
    matched_pattern = None
    for event_type, pattern in EVENT_PATTERNS.items():
        keywords = pattern["keywords"]
        if any(keyword in haystack for keyword in keywords):
            matched_type = event_type
            matched_pattern = pattern
            break

    if not matched_type or not matched_pattern:
        return None

    capacity_match = re.search(r"(\d{2,5})\s?mw", haystack)
    capacity = float(capacity_match.group(1)) if capacity_match else None

    severity = "medium"
    confidence = 0.68
    if capacity and capacity >= 700:
        severity = "high"
        confidence = 0.86
    elif "emergency" in haystack or "scarcity" in haystack:
        severity = "high"
        confidence = 0.82
    elif "advisory" in haystack or "watch" in haystack:
        severity = "medium"
        confidence = 0.64

    region = market_region
    for key, mapped in REGION_MAP.items():
        if key in haystack:
            region = mapped
            break

    direction = str(matched_pattern["price_direction"])
    if matched_type == "regulatory_policy_announcement" and "cap" in haystack:
        direction = "bearish"
    if "return to service" in haystack:
        direction = "bearish"

    now = datetime.now(timezone.utc)
    start_time = now
    expected_end_time = now + timedelta(hours=8 if severity == "high" else 4)

    rationale = (
        f"Tagged as {matched_type.replace('_', ' ')} for {region} based on market-specific keywords"
        f" and a likely {direction} power price effect."
    )

    return ExtractedEvent(
        event_type=matched_type,
        title=title,
        description=body[:500],
        affected_region=region,
        asset_type=str(matched_pattern["asset_type"]),
        capacity_impact_mw=capacity,
        start_time=start_time,
        expected_end_time=expected_end_time,
        severity=severity,
        confidence=confidence,
        price_direction=direction,
        rationale=rationale,
    )
