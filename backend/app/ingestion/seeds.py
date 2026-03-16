from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.news_sources import NEWS_SOURCE_MAP
from app.events.extractor import extract_primary_event
from app.events.impact import estimate_price_impact_pct
from app.models import Alert, DemandPoint, Event, Forecast, Market, NewsArticle, PricePoint, User, UserWatchlist, WeatherPoint


MARKET_DEFINITIONS = [
    {
        "name": "ERCOT North Hub",
        "code": "ERCOT_NORTH",
        "commodity_type": "power",
        "region": "Texas",
        "timezone": "America/Chicago",
        "metadata_json": {
            "nodes": ["HB_NORTH"],
            "market_type": "day_ahead_and_real_time",
            "launch_tier": "core",
        },
        "profile": {
            "demand_base": 42000,
            "demand_amp": 8000,
            "weekday_bias": 2500,
            "weekend_bias": -1000,
            "wind_base": 6500,
            "wind_amp": 1700,
            "solar_base": 4200,
            "temp_base": 22,
            "temp_amp": 10,
            "regional_basis": 0,
        },
    },
    {
        "name": "ERCOT Houston Hub",
        "code": "ERCOT_HOUSTON",
        "commodity_type": "power",
        "region": "Texas",
        "timezone": "America/Chicago",
        "metadata_json": {
            "nodes": ["HB_HOUSTON"],
            "market_type": "day_ahead_and_real_time",
            "launch_tier": "core",
        },
        "profile": {
            "demand_base": 43800,
            "demand_amp": 7800,
            "weekday_bias": 2300,
            "weekend_bias": -900,
            "wind_base": 6000,
            "wind_amp": 1500,
            "solar_base": 3900,
            "temp_base": 24,
            "temp_amp": 9,
            "regional_basis": 3,
        },
    },
    {
        "name": "PJM Western Hub",
        "code": "PJM_WESTERN_HUB",
        "commodity_type": "power",
        "region": "U.S. East Coast",
        "timezone": "America/New_York",
        "metadata_json": {
            "nodes": ["PJM_WEST"],
            "market_type": "day_ahead_and_real_time",
            "launch_tier": "expansion",
            "market_family": "PJM",
        },
        "profile": {
            "demand_base": 54000,
            "demand_amp": 9000,
            "weekday_bias": 3200,
            "weekend_bias": -1800,
            "wind_base": 4200,
            "wind_amp": 1100,
            "solar_base": 2600,
            "temp_base": 18,
            "temp_amp": 11,
            "regional_basis": 7,
        },
    },
    {
        "name": "NYISO Zone J",
        "code": "NYISO_ZONE_J",
        "commodity_type": "power",
        "region": "U.S. East Coast",
        "timezone": "America/New_York",
        "metadata_json": {
            "nodes": ["ZONE_J"],
            "market_type": "day_ahead_and_real_time",
            "launch_tier": "expansion",
            "market_family": "NYISO",
        },
        "profile": {
            "demand_base": 23500,
            "demand_amp": 5200,
            "weekday_bias": 1700,
            "weekend_bias": -700,
            "wind_base": 1800,
            "wind_amp": 500,
            "solar_base": 1100,
            "temp_base": 15,
            "temp_amp": 10,
            "regional_basis": 12,
        },
    },
    {
        "name": "ISO-NE Mass Hub",
        "code": "ISONE_MASS_HUB",
        "commodity_type": "power",
        "region": "U.S. East Coast",
        "timezone": "America/New_York",
        "metadata_json": {
            "nodes": ["MASS_HUB"],
            "market_type": "day_ahead_and_real_time",
            "launch_tier": "expansion",
            "market_family": "ISO-NE",
        },
        "profile": {
            "demand_base": 19500,
            "demand_amp": 4100,
            "weekday_bias": 1200,
            "weekend_bias": -650,
            "wind_base": 3000,
            "wind_amp": 900,
            "solar_base": 1300,
            "temp_base": 14,
            "temp_amp": 10,
            "regional_basis": 10,
        },
    },
    {
        "name": "Great Britain Power Market",
        "code": "GB_POWER",
        "commodity_type": "power",
        "region": "United Kingdom",
        "timezone": "Europe/London",
        "metadata_json": {
            "nodes": ["GB_DA"],
            "market_type": "day_ahead",
            "launch_tier": "expansion",
            "market_family": "GB",
        },
        "profile": {
            "demand_base": 31000,
            "demand_amp": 6200,
            "weekday_bias": 2100,
            "weekend_bias": -1300,
            "wind_base": 7600,
            "wind_amp": 2400,
            "solar_base": 1700,
            "temp_base": 12,
            "temp_amp": 8,
            "regional_basis": 9,
        },
    },
    {
        "name": "EPEX Germany Day-Ahead",
        "code": "EPEX_DE",
        "commodity_type": "power",
        "region": "Germany",
        "timezone": "Europe/Berlin",
        "metadata_json": {
            "nodes": ["EPEX_DE_LU"],
            "market_type": "day_ahead",
            "launch_tier": "expansion",
            "market_family": "EPEX",
        },
        "profile": {
            "demand_base": 56500,
            "demand_amp": 8800,
            "weekday_bias": 2600,
            "weekend_bias": -2100,
            "wind_base": 11200,
            "wind_amp": 3000,
            "solar_base": 6800,
            "temp_base": 13,
            "temp_amp": 9,
            "regional_basis": 6,
        },
    },
    {
        "name": "EPEX France Day-Ahead",
        "code": "EPEX_FR",
        "commodity_type": "power",
        "region": "France",
        "timezone": "Europe/Paris",
        "metadata_json": {
            "nodes": ["EPEX_FR"],
            "market_type": "day_ahead",
            "launch_tier": "expansion",
            "market_family": "EPEX",
        },
        "profile": {
            "demand_base": 47200,
            "demand_amp": 7200,
            "weekday_bias": 2200,
            "weekend_bias": -1800,
            "wind_base": 5600,
            "wind_amp": 1500,
            "solar_base": 4100,
            "temp_base": 14,
            "temp_amp": 8,
            "regional_basis": 5,
        },
    },
    {
        "name": "Nord Pool SE3",
        "code": "NORDPOOL_SE3",
        "commodity_type": "power",
        "region": "Nordics",
        "timezone": "Europe/Stockholm",
        "metadata_json": {
            "nodes": ["SE3"],
            "market_type": "day_ahead",
            "launch_tier": "expansion",
            "market_family": "Nord Pool",
        },
        "profile": {
            "demand_base": 15800,
            "demand_amp": 3600,
            "weekday_bias": 800,
            "weekend_bias": -700,
            "wind_base": 7100,
            "wind_amp": 2100,
            "solar_base": 900,
            "temp_base": 9,
            "temp_amp": 9,
            "regional_basis": 4,
        },
    },
]


def seed_database(db: Session) -> None:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    market_map = {market.code: market for market in db.scalars(select(Market))}

    for definition in MARKET_DEFINITIONS:
        if definition["code"] in market_map:
            continue
        market = Market(
            name=definition["name"],
            code=definition["code"],
            commodity_type=definition["commodity_type"],
            region=definition["region"],
            timezone=definition["timezone"],
            metadata_json=definition["metadata_json"],
        )
        db.add(market)
        db.flush()
        market_map[market.code] = market

    rng = np.random.default_rng(7)
    timestamps = [now - timedelta(hours=hour) for hour in range(24 * 14, 0, -1)]
    article_payloads = [
        {
            "title": "ERCOT reports generator outage impacting 820 MW in North Hub",
            "body": "A forced outage has taken 820 MW offline in the ERCOT North Hub during the afternoon ramp.",
            "summary": "ERCOT operating conditions tightened after a generator outage removed material capacity from the North Hub.",
            "source_key": "ercot_official",
            "market_code": "ERCOT_NORTH",
            "published_at": now - timedelta(hours=3),
        },
        {
            "title": "Heat advisory raises peak load risk across Texas",
            "body": "An extreme heat advisory is expected to lift ERCOT load into the evening peak, increasing scarcity risk.",
            "summary": "Weather-driven demand stress remains a top short-term power price driver in Texas.",
            "source_key": "reuters_energy",
            "market_code": "ERCOT_NORTH",
            "published_at": now - timedelta(hours=10),
        },
        {
            "title": "Wind forecast revised lower for West Texas overnight",
            "body": "Analysts revised wind forecast lower, tightening the expected reserve margin across ERCOT.",
            "summary": "Lower wind expectations tighten reserve margins and raise evening price risk across ERCOT.",
            "source_key": "canary_media",
            "market_code": "ERCOT_HOUSTON",
            "published_at": now - timedelta(hours=18),
        },
        {
            "title": "PJM transmission outage tightens Mid-Atlantic imports",
            "body": "A transmission outage in the Mid-Atlantic is expected to constrain transfers and lift PJM Western Hub prices into peak.",
            "summary": "PJM hub pricing can shift quickly when transfer capability tightens around the Mid-Atlantic.",
            "source_key": "pjm_official",
            "market_code": "PJM_WESTERN_HUB",
            "published_at": now - timedelta(hours=5),
        },
        {
            "title": "NYISO heat advisory raises New York City peak demand risk",
            "body": "An extreme heat advisory across New York City could push Zone J demand higher during the afternoon and evening ramp.",
            "summary": "NYISO Zone J remains especially sensitive when weather lifts New York City peak demand.",
            "source_key": "nyiso_official",
            "market_code": "NYISO_ZONE_J",
            "published_at": now - timedelta(hours=7),
        },
        {
            "title": "ISO-New England generator outage removes 460 MW near Mass Hub",
            "body": "A generator outage near Mass Hub is keeping supply conditions tighter than expected ahead of the morning peak.",
            "summary": "Mass Hub conditions tighten when generator outages overlap the load ramp in New England.",
            "source_key": "isone_official",
            "market_code": "ISONE_MASS_HUB",
            "published_at": now - timedelta(hours=9),
        },
        {
            "title": "Britain wind forecast revised lower ahead of evening demand pickup",
            "body": "A renewable forecast revision points to lower wind output across Great Britain, increasing balancing tightness tonight.",
            "summary": "Lower wind output can materially change UK balancing conditions over the evening peak.",
            "source_key": "neso_official",
            "market_code": "GB_POWER",
            "published_at": now - timedelta(hours=6),
        },
        {
            "title": "German day-ahead power curve firms as wind profile softens",
            "body": "Power traders are reassessing the German day-ahead balance after a softer wind outlook reduced expected renewable output.",
            "summary": "German day-ahead prices often respond quickly to renewable forecast revisions and cross-border constraints.",
            "source_key": "montel",
            "market_code": "EPEX_DE",
            "published_at": now - timedelta(hours=4),
        },
        {
            "title": "RTE signale une tension reseau plus forte sur les echanges frontaliers",
            "body": "Le gestionnaire du reseau francais indique que certaines capacites d echange restent plus contraintes a court terme.",
            "summary": "French cross-border conditions remain tighter than usual over the near term.",
            "translated_title": "RTE flags tighter short-term cross-border network conditions",
            "translated_summary": "Auto-translated summary: the French grid operator is warning that some cross-border exchange capacity remains tighter than normal in the near term.",
            "original_language": "fr",
            "source_key": "rte_france",
            "market_code": "EPEX_FR",
            "published_at": now - timedelta(hours=8),
        },
        {
            "title": "Bundesnetzagentur weist auf anhaltende Netzengpasse hin",
            "body": "Die Bundesnetzagentur betont, dass regionale Engpasse weiter beobachtet werden muessen.",
            "summary": "German grid congestion remains a live monitoring issue for market participants.",
            "translated_title": "Bundesnetzagentur points to ongoing grid bottlenecks",
            "translated_summary": "Auto-translated summary: Germany's regulator says regional transmission bottlenecks still need close monitoring.",
            "original_language": "de",
            "source_key": "bundesnetzagentur",
            "market_code": "EPEX_DE",
            "published_at": now - timedelta(hours=11),
        },
        {
            "title": "Nordic hydro and wind balance shifts keep SE3 traders focused on prompt risk",
            "body": "The Nordic power balance remains sensitive to hydro and wind revisions, keeping the prompt curve reactive.",
            "summary": "Nordic prompt pricing remains highly sensitive to hydro and wind revisions.",
            "source_key": "nord_pool",
            "market_code": "NORDPOOL_SE3",
            "published_at": now - timedelta(hours=13),
        },
        {
            "title": "EPEX SPOT highlights continued volatility in European day-ahead trading",
            "body": "Exchange-level commentary points to persistent sensitivity around renewable variability and interconnection limits.",
            "summary": "European day-ahead power remains highly reactive to renewables and interconnection flows.",
            "source_key": "epex_spot",
            "market_code": "EPEX_DE",
            "published_at": now - timedelta(hours=15),
        },
        {
            "title": "Red Electrica subraya cambios en el equilibrio peninsular de corto plazo",
            "body": "El operador del sistema destaca cambios recientes en el balance peninsular y su impacto operativo.",
            "summary": "Spanish short-term system balance remains fluid.",
            "translated_title": "Red Electrica highlights short-term changes in the Iberian system balance",
            "translated_summary": "Auto-translated summary: Spain's system operator points to recent shifts in the short-term peninsula balance with operational impact.",
            "original_language": "es",
            "source_key": "ree",
            "market_code": "GB_POWER",
            "published_at": now - timedelta(hours=16),
        },
    ]

    for market in market_map.values():
        profile = next(item["profile"] for item in MARKET_DEFINITIONS if item["code"] == market.code)
        has_prices = db.scalar(select(func.count()).select_from(PricePoint).where(PricePoint.market_id == market.id))
        if has_prices:
            continue
        for ts in timestamps:
            hour = ts.hour
            day = ts.weekday()
            temp = profile["temp_base"] + profile["temp_amp"] * np.sin((hour / 24) * 2 * np.pi) + rng.normal(0, 1.5)
            demand = (
                profile["demand_base"]
                + profile["demand_amp"] * np.sin(((hour - 7) / 24) * 2 * np.pi)
                + (profile["weekday_bias"] if day < 5 else profile["weekend_bias"])
                + rng.normal(0, 850)
            )
            wind = profile["wind_base"] + profile["wind_amp"] * np.cos((hour / 24) * 2 * np.pi) + rng.normal(0, 400)
            solar = max(0, profile["solar_base"] * np.sin(((hour - 6) / 12) * np.pi)) + rng.normal(0, 140)
            precip = max(0, rng.normal(0.6, 0.7))
            scarcity = 1 if demand > 50000 and wind < 5800 else 0
            basis = 42 + 0.0012 * demand - 0.001 * wind - 0.00045 * solar + 0.15 * max(temp - 30, 0) + 18 * scarcity
            basis += profile["regional_basis"]
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
        source_meta = NEWS_SOURCE_MAP[payload["source_key"]]
        existing_article = db.scalar(select(NewsArticle).where(NewsArticle.title == payload["title"]))
        raw_json = {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in payload.items()
        }
        raw_json.update(
            {
                "source_url": source_meta["url"],
                "source_name": source_meta["name"],
                "credibility_rating": source_meta["credibility_rating"],
                "credibility_label": source_meta["credibility_label"],
                "source_homepage": source_meta["url"],
                "notes": source_meta["notes"],
                "original_language": payload.get("original_language", source_meta["language"]),
            }
        )
        if existing_article:
            article = existing_article
            article.body = payload["body"]
            article.source_name = source_meta["name"]
            article.source_url = source_meta["url"]
            article.published_at = payload["published_at"]
            article.raw_json = raw_json
            article.processed_status = "processed"
        else:
            article = NewsArticle(
                title=payload["title"],
                body=payload["body"],
                source_name=source_meta["name"],
                source_url=source_meta["url"],
                published_at=payload["published_at"],
                raw_json=raw_json,
                processed_status="processed",
            )
            db.add(article)
            db.flush()

        market = market_map.get(payload["market_code"])
        extracted = extract_primary_event(payload["title"], payload["body"], market.region if market else "ERCOT")
        existing_event = db.scalar(select(Event).where(Event.article_id == article.id))
        if extracted and not existing_event:
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
    if not db.scalar(select(User.id).where(User.email == demo_user.email)):
        db.add(demo_user)
        db.flush()
        db.add(
            UserWatchlist(
                user_id=demo_user.id,
                market_id=market_map["ERCOT_NORTH"].id,
                configuration_json={"alert_preferences": ["spike_risk", "outage", "policy"]},
            )
        )

    alerts = [
        Alert(
            market_id=market_map["ERCOT_NORTH"].id,
            alert_type="spike_risk",
            title="Spike probability elevated into evening peak",
            body="Demand is running above trend while a generator outage keeps reserve margins tighter than normal.",
            severity="high",
        ),
        Alert(
            market_id=market_map["ERCOT_NORTH"].id,
            alert_type="outage",
            title="North Hub outage remains active",
            body="The largest current structured event is an 820 MW generator outage with a bullish local price bias.",
            severity="medium",
        ),
        Alert(
            market_id=market_map["PJM_WESTERN_HUB"].id,
            alert_type="constraint",
            title="Mid-Atlantic transmission constraint active",
            body="A PJM transmission event is tightening transfer capability and skewing local prices higher into peak hours.",
            severity="medium",
        ),
        Alert(
            market_id=market_map["GB_POWER"].id,
            alert_type="renewables",
            title="Lower UK wind outlook tightens evening balance",
            body="A downward wind revision is lifting the near-term balancing risk profile across Great Britain.",
            severity="medium",
        ),
    ]
    existing_alert_titles = set(db.scalars(select(Alert.title)))
    for alert in alerts:
        if alert.title not in existing_alert_titles:
            db.add(alert)
    db.flush()

    for market in market_map.values():
        has_forecasts = db.scalar(select(func.count()).select_from(Forecast).where(Forecast.market_id == market.id))
        if has_forecasts:
            continue
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
