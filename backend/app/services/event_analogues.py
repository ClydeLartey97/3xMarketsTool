from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.extractor import EVENT_PATTERNS
from app.models import Event


EVENT_TYPES = sorted(EVENT_PATTERNS)
REGIMES = ["calm", "trending", "stressed"]


def find_analogues(event: Event, db: Session, k: int = 5) -> list[Event]:
    candidates = list(
        db.scalars(
            select(Event)
            .where(Event.id != event.id)
            .order_by(Event.created_at.desc())
            .limit(500)
        ).all()
    )
    target_vector = _event_vector(event)
    scored: list[tuple[float, Event]] = []
    for candidate in candidates:
        score = _cosine(target_vector, _event_vector(candidate))
        if score > 0:
            scored.append((score, candidate))
    scored.sort(
        key=lambda item: (item[0], item[1].created_at or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    return [candidate for _, candidate in scored[: max(0, int(k))]]


def populate_event_analogues(event: Event, db: Session, k: int = 5) -> list[int]:
    analogues = find_analogues(event, db, k=k)
    analogue_ids = [item.id for item in analogues if item.id is not None]
    event.analogue_event_ids = analogue_ids
    return analogue_ids


def _event_vector(event: Event) -> list[float]:
    ts = _event_time(event)
    magnitude = float(event.magnitude_mw or event.capacity_impact_mw or 0.0)
    magnitude_scaled = min(1.0, math.log1p(max(0.0, magnitude)) / math.log1p(5000.0))
    hour = ts.hour
    day = ts.weekday()
    regime = _event_regime(event)
    return [
        *[1.0 if event.event_type == event_type else 0.0 for event_type in EVENT_TYPES],
        magnitude_scaled,
        math.sin((hour / 24.0) * 2 * math.pi),
        math.cos((hour / 24.0) * 2 * math.pi),
        math.sin((day / 7.0) * 2 * math.pi),
        math.cos((day / 7.0) * 2 * math.pi),
        *[1.0 if regime == item else 0.0 for item in REGIMES],
    ]


def _event_time(event: Event) -> datetime:
    value = event.start_time or event.created_at or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_regime(event: Event) -> str:
    if event.severity == "high":
        return "stressed"
    if event.severity == "medium":
        return "trending"
    return "calm"


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)
