from app.events.extractor import extract_primary_event
from app.events.impact import estimate_price_impact_pct


def test_extract_generator_outage_event() -> None:
    event = extract_primary_event(
        "ERCOT generator outage removes 900 MW in North Hub",
        "A forced outage took a large thermal unit offline during the evening ramp.",
    )

    assert event is not None
    assert event.event_type == "generator_outage"
    assert event.severity == "high"
    assert event.price_direction == "bullish"
    assert estimate_price_impact_pct(event) and estimate_price_impact_pct(event) > 0


def test_irrelevant_article_returns_none() -> None:
    event = extract_primary_event(
        "Company announces quarterly earnings",
        "The release discussed software subscriptions and had no grid operations details.",
    )
    assert event is None
