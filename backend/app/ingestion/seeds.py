from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.extractor import extract_primary_event
from app.events.impact import estimate_price_impact_pct
from app.models import Alert, DemandPoint, Event, Forecast, Market, NewsArticle, PricePoint, User, UserWatchlist, WeatherPoint


def seed_database(db: Session) -> None:
    existing_market = db.scalar(select(Market.id).limit(1))
    if existing_market:
        return

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    markets = [
        Market(
            name="ERCOT North Hub",
            code="ERCOT_NORTH",
            commodity_type="power",
            region="Texas",
            timezone="America/Chicago",
            metadata_json={"nodes": ["HB_NORTH"], "market_type": "day_ahead_and_real_time"},
        ),
        Market(
            name="ERCOT Houston Hub",
            code="ERCOT_HOUSTON",
            commodity_type="power",
            region="Texas",
            timezone="America/Chicago",
            metadata_json={"nodes": ["HB_HOUSTON"], "market_type": "day_ahead_and_real_time"},
        ),
    ]
    db.add_all(markets)
    db.flush()

    rng = np.random.default_rng(7)
    timestamps = [now - timedelta(hours=hour) for hour in range(24 * 14, 0, -1)]
    article_payloads = [
        {
            "title": "ERCOT reports generator outage impacting 820 MW in North Hub",
            "body": "A forced outage has taken 820 MW offline in the ERCOT North Hub during the afternoon ramp.",
            "source_name": "Grid Monitor",
            "source_url": "https://example.com/ercot-generator-outage",
            "market_code": "ERCOT_NORTH",
            "published_at": now - timedelta(hours=3),
        },
        {
            "title": "Heat advisory raises peak load risk across Texas",
            "body": "An extreme heat advisory is expected to lift ERCOT load into the evening peak, increasing scarcity risk.",
            "source_name": "Weather Desk",
            "source_url": "https://example.com/heat-advisory",
            "market_code": "ERCOT_NORTH",
            "published_at": now - timedelta(hours=10),
        },
        {
            "title": "Wind forecast revised lower for West Texas overnight",
            "body": "Analysts revised wind forecast lower, tightening the expected reserve margin across ERCOT.",
            "source_name": "Renewables Wire",
            "source_url": "https://example.com/wind-forecast",
            "market_code": "ERCOT_HOUSTON",
            "published_at": now - timedelta(hours=18),
        },
    ]

    for market in markets:
        for ts in timestamps:
            hour = ts.hour
            day = ts.weekday()
            temp = 22 + 10 * np.sin((hour / 24) * 2 * np.pi) + rng.normal(0, 1.5)
            demand = 42000 + 8000 * np.sin(((hour - 7) / 24) * 2 * np.pi) + (2500 if day < 5 else -1000) + rng.normal(0, 850)
            wind = 6500 + 1700 * np.cos((hour / 24) * 2 * np.pi) + rng.normal(0, 400)
            solar = max(0, 4200 * np.sin(((hour - 6) / 12) * np.pi)) + rng.normal(0, 140)
            precip = max(0, rng.normal(0.6, 0.7))
            scarcity = 1 if demand > 50000 and wind < 5800 else 0
            basis = 42 + 0.0012 * demand - 0.001 * wind - 0.00045 * solar + 0.15 * max(temp - 30, 0) + 18 * scarcity
            basis += 3 if market.code == "ERCOT_HOUSTON" else 0
            price = basis + rng.normal(0, 5.5)

            db.add(
                PricePoint(
                    market_id=market.id,
                    timestamp=ts,
                    horizon_type="spot",
                    price_value=round(float(price), 2),
                    source="synthetic_seed",
                )
            )
            db.add(
                WeatherPoint(
                    market_id=market.id,
                    timestamp=ts,
                    temperature_c=round(float(temp), 2),
                    wind_speed=round(float(max(2, wind / 650)), 2),
                    wind_generation_estimate=round(float(max(1000, wind)), 2),
                    solar_generation_estimate=round(float(max(0, solar)), 2),
                    precipitation=round(float(precip), 2),
                    source="synthetic_seed",
                )
            )
            db.add(
                DemandPoint(
                    market_id=market.id,
                    timestamp=ts,
                    demand_mw=round(float(max(25000, demand)), 2),
                    source="synthetic_seed",
                )
            )

    db.flush()

    for payload in article_payloads:
        raw_json = {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in payload.items()
        }
        article = NewsArticle(
            title=payload["title"],
            body=payload["body"],
            source_name=payload["source_name"],
            source_url=payload["source_url"],
            published_at=payload["published_at"],
            raw_json=raw_json,
            processed_status="processed",
        )
        db.add(article)
        db.flush()

        market = db.scalar(select(Market).where(Market.code == payload["market_code"]))
        extracted = extract_primary_event(payload["title"], payload["body"], market.region if market else "ERCOT")
        if extracted:
            db.add(
                Event(
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
            )

    demo_user = User(
        email="demo@3x.local",
        password_hash="demo-only",
        organisation="3x Demo",
        role="analyst",
    )
    db.add(demo_user)
    db.flush()
    db.add(
        UserWatchlist(
            user_id=demo_user.id,
            market_id=markets[0].id,
            configuration_json={"alert_preferences": ["spike_risk", "outage", "policy"]},
        )
    )

    alerts = [
        Alert(
            market_id=markets[0].id,
            alert_type="spike_risk",
            title="Spike probability elevated into evening peak",
            body="Demand is running above trend while a generator outage keeps reserve margins tighter than normal.",
            severity="high",
        ),
        Alert(
            market_id=markets[0].id,
            alert_type="outage",
            title="North Hub outage remains active",
            body="The largest current structured event is an 820 MW generator outage with a bullish local price bias.",
            severity="medium",
        ),
    ]
    db.add_all(alerts)
    db.flush()

    for market in markets:
        latest_price = db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id)
            .order_by(PricePoint.timestamp.desc())
            .limit(1)
        ).first()
        if not latest_price:
            continue
        for step in range(1, 25):
            ts = latest_price.timestamp + timedelta(hours=step)
            point = latest_price.price_value + (1.5 * np.sin(step / 3.0)) + (5 if step in (18, 19, 20) else 0)
            spike = min(0.8, 0.12 + (0.08 if step in (18, 19, 20) else 0.02))
            db.add(
                Forecast(
                    market_id=market.id,
                    forecast_for_timestamp=ts,
                    point_estimate=round(float(point), 2),
                    lower_bound=round(float(point - 9), 2),
                    upper_bound=round(float(point + 9), 2),
                    spike_probability=round(float(spike), 3),
                    model_version="seed-v1",
                    rationale_summary="Forecast is elevated due to expected evening demand and tighter supply conditions.",
                    feature_snapshot_json={"seeded": True, "step": step},
                )
            )

    db.commit()
