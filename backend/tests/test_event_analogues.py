from __future__ import annotations

from datetime import datetime, timezone

from app.models import Event
from app.services.event_analogues import find_analogues, populate_event_analogues


def _event(**overrides) -> Event:
    base = {
        "event_type": "generator_outage",
        "title": "Generator outage removes capacity",
        "description": "A forced outage removed capacity before peak.",
        "affected_region": "ERCOT",
        "asset_type": "generation",
        "capacity_impact_mw": 900.0,
        "zone": "ERCOT",
        "node": "North Hub",
        "magnitude_mw": 900.0,
        "duration_hours_estimate": 8.0,
        "duration_hours_p10": 4.0,
        "duration_hours_p90": 12.0,
        "analogue_event_ids": [],
        "classifier_version": "heuristic-v2",
        "start_time": datetime(2026, 5, 10, 18, tzinfo=timezone.utc),
        "expected_end_time": datetime(2026, 5, 11, 2, tzinfo=timezone.utc),
        "severity": "high",
        "confidence": 0.86,
        "price_direction": "bullish",
        "estimated_price_impact_pct": 8.0,
        "rationale": "unit test",
        "created_at": datetime(2026, 5, 10, 17, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return Event(**base)


def test_find_analogues_prefers_similar_past_events(db_session) -> None:
    similar = _event(title="Similar outage", magnitude_mw=880.0, capacity_impact_mw=880.0)
    unrelated = _event(
        event_type="regulatory_policy_announcement",
        title="Policy filing",
        asset_type="policy",
        severity="low",
        magnitude_mw=None,
        capacity_impact_mw=None,
        start_time=datetime(2026, 5, 7, 3, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 7, 2, tzinfo=timezone.utc),
        price_direction="uncertain",
    )
    target = _event(
        title="Target outage",
        start_time=datetime(2026, 5, 10, 18, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 10, 18, tzinfo=timezone.utc),
    )
    db_session.add_all([similar, unrelated, target])
    db_session.commit()

    analogues = find_analogues(target, db_session, k=2)

    assert analogues[0].id == similar.id

    analogue_ids = populate_event_analogues(target, db_session, k=2)
    assert analogue_ids[0] == similar.id
    assert target.analogue_event_ids[0] == similar.id
