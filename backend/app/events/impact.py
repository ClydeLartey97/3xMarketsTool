from __future__ import annotations

from app.events.extractor import ExtractedEvent


def estimate_price_impact_pct(event: ExtractedEvent) -> float | None:
    base = {
        "generator_outage": 4.5,
        "transmission_outage": 3.8,
        "extreme_weather_alert": 2.6,
        "renewable_forecast_revision": 2.2,
        "demand_shock": 2.9,
        "regulatory_policy_announcement": 1.0,
    }.get(event.event_type, 1.0)

    if event.capacity_impact_mw:
        base += min(event.capacity_impact_mw / 400.0, 4.5)

    if event.severity == "high":
        base *= 1.25
    elif event.severity == "low":
        base *= 0.7

    if event.price_direction == "bearish":
        return round(-base, 2)
    if event.price_direction == "uncertain":
        return round(base * 0.35, 2)
    return round(base, 2)
