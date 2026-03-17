from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import delete, func, select
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

SYNTHETIC_SEED_SOURCE = "synthetic_seed_v2"

MARKET_SYNTHETIC_SHAPES = {
    "ERCOT_NORTH": {
        "demand_peak_hour": 18,
        "morning_peak_hour": 8,
        "morning_peak_mw": 1300,
        "evening_peak_hour": 19,
        "evening_peak_mw": 2600,
        "wind_peak_hour": 2,
        "solar_rise_hour": 7,
        "solar_daylight_hours": 12,
        "price_noise_scale": 1.0,
        "solar_price_discount": 1.0,
    },
    "ERCOT_HOUSTON": {
        "demand_peak_hour": 19,
        "morning_peak_hour": 8,
        "morning_peak_mw": 900,
        "evening_peak_hour": 20,
        "evening_peak_mw": 3000,
        "wind_peak_hour": 1,
        "solar_rise_hour": 7,
        "solar_daylight_hours": 12,
        "price_noise_scale": 1.08,
        "solar_price_discount": 0.8,
    },
    "PJM_WESTERN_HUB": {
        "demand_peak_hour": 17,
        "morning_peak_hour": 9,
        "morning_peak_mw": 900,
        "evening_peak_hour": 18,
        "evening_peak_mw": 1700,
        "wind_peak_hour": 0,
        "solar_rise_hour": 7,
        "solar_daylight_hours": 11,
        "price_noise_scale": 0.96,
        "solar_price_discount": 0.7,
    },
    "NYISO_ZONE_J": {
        "demand_peak_hour": 18,
        "morning_peak_hour": 8,
        "morning_peak_mw": 1100,
        "evening_peak_hour": 19,
        "evening_peak_mw": 2100,
        "wind_peak_hour": 23,
        "solar_rise_hour": 7,
        "solar_daylight_hours": 11,
        "price_noise_scale": 1.05,
        "solar_price_discount": 0.6,
    },
    "ISONE_MASS_HUB": {
        "demand_peak_hour": 18,
        "morning_peak_hour": 8,
        "morning_peak_mw": 1500,
        "evening_peak_hour": 18,
        "evening_peak_mw": 1900,
        "wind_peak_hour": 23,
        "solar_rise_hour": 7,
        "solar_daylight_hours": 10,
        "price_noise_scale": 1.12,
        "solar_price_discount": 0.55,
    },
    "GB_POWER": {
        "demand_peak_hour": 17,
        "morning_peak_hour": 8,
        "morning_peak_mw": 1200,
        "evening_peak_hour": 17,
        "evening_peak_mw": 2200,
        "wind_peak_hour": 1,
        "solar_rise_hour": 8,
        "solar_daylight_hours": 10,
        "price_noise_scale": 1.15,
        "solar_price_discount": 0.45,
    },
    "EPEX_DE": {
        "demand_peak_hour": 18,
        "morning_peak_hour": 8,
        "morning_peak_mw": 700,
        "evening_peak_hour": 19,
        "evening_peak_mw": 1400,
        "wind_peak_hour": 2,
        "solar_rise_hour": 6,
        "solar_daylight_hours": 13,
        "price_noise_scale": 1.18,
        "solar_price_discount": 1.45,
    },
    "EPEX_FR": {
        "demand_peak_hour": 19,
        "morning_peak_hour": 8,
        "morning_peak_mw": 650,
        "evening_peak_hour": 19,
        "evening_peak_mw": 1250,
        "wind_peak_hour": 3,
        "solar_rise_hour": 7,
        "solar_daylight_hours": 12,
        "price_noise_scale": 1.03,
        "solar_price_discount": 0.95,
    },
    "NORDPOOL_SE3": {
        "demand_peak_hour": 8,
        "morning_peak_hour": 8,
        "morning_peak_mw": 1200,
        "evening_peak_hour": 17,
        "evening_peak_mw": 900,
        "wind_peak_hour": 4,
        "solar_rise_hour": 8,
        "solar_daylight_hours": 9,
        "price_noise_scale": 1.08,
        "solar_price_discount": 0.3,
    },
}

CURVE_SOURCE_MAP = {
    "ERCOT_NORTH": {
        "label": "ERCOT market dashboards",
        "url": "https://www.ercot.com/gridmktinfo/dashboards",
        "kind": "official_operator",
    },
    "ERCOT_HOUSTON": {
        "label": "ERCOT market dashboards",
        "url": "https://www.ercot.com/gridmktinfo/dashboards",
        "kind": "official_operator",
    },
    "PJM_WESTERN_HUB": {
        "label": "PJM markets and operations",
        "url": "https://www.pjm.com/markets-and-operations.aspx",
        "kind": "official_operator",
    },
    "NYISO_ZONE_J": {
        "label": "NYISO market operational data",
        "url": "https://www.nyiso.com/energy-market-operational-data",
        "kind": "official_operator",
    },
    "ISONE_MASS_HUB": {
        "label": "ISO-NE ISO Express",
        "url": "https://www.iso-ne.com/isoexpress/",
        "kind": "official_operator",
    },
    "GB_POWER": {
        "label": "NESO data portal",
        "url": "https://www.neso.energy/data-portal",
        "kind": "official_operator",
    },
    "EPEX_DE": {
        "label": "EPEX SPOT market data",
        "url": "https://www.epexspot.com/en/market-data",
        "kind": "official_exchange",
    },
    "EPEX_FR": {
        "label": "EPEX SPOT market data",
        "url": "https://www.epexspot.com/en/market-data",
        "kind": "official_exchange",
    },
    "NORDPOOL_SE3": {
        "label": "Nord Pool market data",
        "url": "https://www.nordpoolgroup.com/en/Market-data1/",
        "kind": "official_exchange",
    },
}


def seed_database(db: Session) -> None:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    market_map = {market.code: market for market in db.scalars(select(Market))}

    for definition in MARKET_DEFINITIONS:
        if definition["code"] in market_map:
            market = market_map[definition["code"]]
            merged_metadata = {
                **(market.metadata_json or {}),
                **definition["metadata_json"],
                "profile": MARKET_SYNTHETIC_SHAPES.get(definition["code"], {}),
                "curve_source": CURVE_SOURCE_MAP.get(definition["code"], {}),
            }
            if market.metadata_json != merged_metadata:
                market.metadata_json = merged_metadata
            continue
        market = Market(
            name=definition["name"],
            code=definition["code"],
            commodity_type=definition["commodity_type"],
            region=definition["region"],
            timezone=definition["timezone"],
            metadata_json={
                **definition["metadata_json"],
                "profile": MARKET_SYNTHETIC_SHAPES.get(definition["code"], {}),
                "curve_source": CURVE_SOURCE_MAP.get(definition["code"], {}),
            },
        )
        db.add(market)
        db.flush()
        market_map[market.code] = market

    rng = np.random.default_rng(7)
    timestamps = [now - timedelta(hours=hour) for hour in range(24 * 14, 0, -1)]
    article_payloads = [
        {
            "seed_key": "ercot-load-growth-utility-dive",
            "title": "Rising U.S. load growth sharpens forward power risk in Texas",
            "body": "Utility Dive highlights demand growth from data centers and stronger peak demand expectations, a demand growth signal that can keep ERCOT scarcity risk elevated.",
            "summary": "Large-load growth is becoming a durable bullish signal for tight power systems such as ERCOT.",
            "source_key": "utility_dive",
            "market_code": "ERCOT_NORTH",
            "source_url": "https://www.utilitydive.com/news/energy-short-term-outlook-2026-load-demand-data-centers/807530/",
            "published_at": now - timedelta(hours=2),
        },
        {
            "seed_key": "ercot-load-growth-spglobal",
            "title": "Data-center power demand lifts reliability stress across fast-growth grids",
            "body": "S&P Global Commodity Insights says data center demand growth could accelerate grid stress, a large load signal that matters for Houston reserve margins and forward power risk.",
            "summary": "Structural load growth is becoming a non-weather driver of power-price risk in high-growth U.S. hubs.",
            "source_key": "spglobal_power",
            "market_code": "ERCOT_HOUSTON",
            "source_url": "https://www.spglobal.com/commodityinsights/en/market-insights/latest-news/electric-power/101425-data-center-grid-power-demand-to-rise-22-in-2025-nearly-triple-by-2030",
            "published_at": now - timedelta(hours=4),
        },
        {
            "seed_key": "pjm-price-collar-pjm",
            "title": "PJM files large-load plan with price collar and expedited interconnection",
            "body": "PJM filed a market rule change that adds a price collar and expedited interconnection process for large load requests, highlighting demand growth and future scarcity risk.",
            "summary": "PJM is explicitly adjusting market design around fast-rising large-load demand.",
            "source_key": "pjm_official",
            "market_code": "PJM_WESTERN_HUB",
            "source_url": "https://insidelines.pjm.com/pjm-files-price-collar-expedited-interconnection-as-part-of-large-load-plan/",
            "published_at": now - timedelta(hours=3),
        },
        {
            "seed_key": "pjm-load-outlook-power-mag",
            "title": "PJM load growth still points to a structurally tighter forward balance",
            "body": "POWER Magazine says PJM still expects steep load growth, a demand growth shock that keeps Western Hub forward pricing sensitive to reserve tightening.",
            "summary": "Even a slightly softer near-term outlook still leaves PJM with a strong structural load-growth story.",
            "source_key": "power_mag",
            "market_code": "PJM_WESTERN_HUB",
            "source_url": "https://www.powermag.com/pjm-dials-back-near-term-load-outlook-but-maintains-steep-long-term-growth-trajectory/",
            "published_at": now - timedelta(hours=6),
        },
        {
            "seed_key": "pjm-court-rto-insider",
            "title": "Court ruling keeps scrutiny on PJM post-auction rule changes",
            "body": "RTO Insider says PJM market rule change risk remains elevated after the latest court ruling, keeping capacity pricing and forward signals in focus.",
            "summary": "PJM's auction design and rule stability remain market-moving inputs for traders.",
            "source_key": "rto_insider",
            "market_code": "PJM_WESTERN_HUB",
            "source_url": "https://www.rtoinsider.com/73697-3rd-circuit-rules-pjm-post-auction-change/",
            "published_at": now - timedelta(hours=9),
        },
        {
            "seed_key": "nyiso-heatwave-official",
            "title": "NYISO prepares for heatwave as Zone J demand risk rises",
            "body": "NYISO says the grid is prepared for a forecasted heatwave, but the heat advisory still points to higher peak demand risk in New York City.",
            "summary": "Zone J remains one of the most weather-sensitive U.S. pricing locations during heat events.",
            "source_key": "nyiso_official",
            "market_code": "NYISO_ZONE_J",
            "source_url": "https://www.nyiso.com/-/press-release-new-york-electric-grid-prepared-for-forecasted-heatwave",
            "published_at": now - timedelta(hours=5),
        },
        {
            "seed_key": "isone-summer-outlook",
            "title": "ISO New England summer outlook flags higher stress in extreme heat intervals",
            "body": "ISO New England's summer outlook points to tighter operating conditions during extreme heat and peak demand intervals around Mass Hub.",
            "summary": "ISO-NE remains especially sensitive when weather and evening ramp conditions coincide.",
            "source_key": "isone_official",
            "market_code": "ISONE_MASS_HUB",
            "source_url": "https://www.iso-ne.com/about/news/2026/06/iso-ne-is-ready-for-summer-2026-electricity-demand-and-grid-operations",
            "published_at": now - timedelta(hours=7),
        },
        {
            "seed_key": "gb-grid-connections-neso",
            "title": "NESO grid-connection reforms reshape the British forward risk map",
            "body": "NESO's grid connections reform is a market rule change intended to accelerate projects and rebalance how future supply reaches Great Britain.",
            "summary": "Britain's grid queue is becoming a market signal, not just an infrastructure story.",
            "source_key": "neso_official",
            "market_code": "GB_POWER",
            "source_url": "https://www.neso.energy/neso-implements-electricity-grid-connection-reforms-unlock-investment-great-britain",
            "published_at": now - timedelta(hours=8),
        },
        {
            "seed_key": "gb-connections-ofgem",
            "title": "Ofgem fast-track connection plan adds policy momentum to Great Britain supply timing",
            "body": "Ofgem unveiled a fast-track grid connections action plan, a policy announcement that could reshape project queues and future British supply timing.",
            "summary": "Regulatory action on connection queues is now a material long-term signal for UK power traders.",
            "source_key": "ofgem",
            "market_code": "GB_POWER",
            "source_url": "https://www.ofgem.gov.uk/press-release/clean-power-2030-one-step-closer-proposed-new-fast-track-grid-connections-system-unveiled",
            "published_at": now - timedelta(hours=10),
        },
        {
            "seed_key": "germany-negative-prices-bloomberg",
            "title": "Record solar output pushes continental power curves deeper into negative pricing",
            "body": "Bloomberg reports French power prices moved negative on record solar output, a renewable forecast revision signal spilling into Germany and the broader EPEX curve.",
            "summary": "Record solar and weak prompt demand are reshaping continental day-ahead price formation.",
            "source_key": "bloomberg_energy",
            "market_code": "EPEX_DE",
            "source_url": "https://www.bloomberg.com/news/articles/2025-07-10/french-power-prices-go-negative-with-solar-output-at-record",
            "published_at": now - timedelta(hours=11),
        },
        {
            "seed_key": "germany-negative-prices-montel",
            "title": "Negative and zero prices remain a live renewable-balancing signal in Europe",
            "body": "Montel says negative and zero prices in Europe's power markets are being driven by renewable variability and softer wind profile assumptions.",
            "summary": "European day-ahead curves are increasingly shaped by renewable oversupply windows and grid constraints.",
            "source_key": "montel",
            "market_code": "EPEX_DE",
            "source_url": "https://montel.energy/resources/reports/negative-and-zero-prices-in-europes-power-markets",
            "published_at": now - timedelta(hours=12),
        },
        {
            "seed_key": "epex-15m-products",
            "title": "EPEX SPOT expands 15-minute products and sharpens intraday market design",
            "body": "EPEX SPOT says 15-minute products are live in day-ahead markets, a market rule change with direct impact on short-term liquidity and power curve formation.",
            "summary": "Exchange design is becoming a real part of the short-term trading edge in continental power.",
            "source_key": "epex_spot",
            "market_code": "EPEX_DE",
            "source_url": "https://www.epexspot.com/en/news/15-minute-products-live-epex-spot-day-ahead-markets",
            "published_at": now - timedelta(hours=13),
        },
        {
            "seed_key": "rte-france-uk-interconnector",
            "title": "RTE updates the France-UK interconnection path",
            "body": "RTE publie une consultation sur l interconnexion France Angleterre, une annonce de politique de reseau qui compte pour la liquidite frontaliere et la formation des prix.",
            "summary": "French cross-border transmission policy remains a real pricing input for continental traders.",
            "translated_title": "RTE updates the France-UK interconnection path",
            "translated_summary": "Auto-translated summary: France's grid operator is consulting on the France-UK interconnector, a cross-border policy signal that can matter for regional price formation.",
            "original_language": "fr",
            "source_key": "rte_france",
            "market_code": "EPEX_FR",
            "source_url": "https://www.rte-france.com/en/eco2mix/interconnexion-france-angleterre-rte-renouvelle-la-liaison-i-fa2",
            "published_at": now - timedelta(hours=14),
        },
        {
            "seed_key": "acer-market-integration",
            "title": "ACER pushes faster market integration to absorb volatility",
            "body": "ACER says more flexibility and faster electricity market integration are needed, a policy announcement that matters for French and German day-ahead risk transfer.",
            "summary": "EU market-design changes are becoming first-order inputs for continental power traders.",
            "source_key": "acer",
            "market_code": "EPEX_FR",
            "source_url": "https://www.acer.europa.eu/news/more-flexibility-and-faster-eu-electricity-market-integration-needed-shield-consumers-price-volatility-and-support-clean-energy-transition",
            "published_at": now - timedelta(hours=16),
        },
        {
            "seed_key": "nordpool-flow-based",
            "title": "Nord Pool flow-based coupling changes the Nordic prompt setup",
            "body": "Nord Pool says Nordic flow-based market coupling has gone live, a market integration change with direct implications for SE3 price formation and cross-border flows.",
            "summary": "Nordic prompt power is becoming more sensitive to market-coupling mechanics and transfer capacity.",
            "source_key": "nord_pool",
            "market_code": "NORDPOOL_SE3",
            "source_url": "https://www.nordpoolgroup.com/en/message-center-container/newsroom/exchange-message-list/2024/q4/successful-go-live-of-the-nordic-flow-based-market-coupling-project/",
            "published_at": now - timedelta(hours=18),
        },
        {
            "seed_key": "entsoe-adequacy-assessment",
            "title": "ENTSO-E adequacy work keeps interconnections and flexibility at the center of risk",
            "body": "ENTSO-E says updated market rules, interconnections, and flexibility solutions are needed to maintain security of supply across Europe.",
            "summary": "Security-of-supply assessments still matter for prompt Nordic and continental positioning.",
            "source_key": "entsoe",
            "market_code": "NORDPOOL_SE3",
            "source_url": "https://www.entsoe.eu/news/2025/04/07/european-resource-adequacy-assessment-interconnections-flexibility-solutions-and-updated-market-rules-to-maintain-high-level-of-electricity-supply-security/",
            "published_at": now - timedelta(hours=20),
        },
    ]
    pair_counts: dict[tuple[str, str], int] = {}
    for payload in article_payloads:
        key = (payload["source_key"], payload["market_code"])
        pair_counts[key] = pair_counts.get(key, 0) + 1

    for market in market_map.values():
        profile = next(item["profile"] for item in MARKET_DEFINITIONS if item["code"] == market.code)
        shape = MARKET_SYNTHETIC_SHAPES.get(market.code, MARKET_SYNTHETIC_SHAPES["ERCOT_NORTH"])
        current_seed_rows = db.scalar(
            select(func.count()).select_from(PricePoint).where(
                PricePoint.market_id == market.id,
                PricePoint.source == SYNTHETIC_SEED_SOURCE,
            )
        )
        legacy_seed_rows = db.scalar(
            select(func.count()).select_from(PricePoint).where(
                PricePoint.market_id == market.id,
                PricePoint.source.like("synthetic_seed%"),
            )
        )
        if current_seed_rows:
            continue
        if legacy_seed_rows:
            db.execute(delete(Forecast).where(Forecast.market_id == market.id))
            db.execute(delete(PricePoint).where(PricePoint.market_id == market.id, PricePoint.source.like("synthetic_seed%")))
            db.execute(delete(WeatherPoint).where(WeatherPoint.market_id == market.id, WeatherPoint.source.like("synthetic_seed%")))
            db.execute(delete(DemandPoint).where(DemandPoint.market_id == market.id, DemandPoint.source.like("synthetic_seed%")))
            db.flush()
        for ts in timestamps:
            hour = ts.hour
            day = ts.weekday()
            morning_peak = shape["morning_peak_mw"] * np.exp(-(((hour - shape["morning_peak_hour"]) ** 2) / 6.0))
            evening_peak = shape["evening_peak_mw"] * np.exp(-(((hour - shape["evening_peak_hour"]) ** 2) / 8.0))
            temp = profile["temp_base"] + profile["temp_amp"] * np.sin(((hour - 4) / 24) * 2 * np.pi) + rng.normal(0, 1.5)
            demand = (
                profile["demand_base"]
                + profile["demand_amp"] * np.sin(((hour - shape["demand_peak_hour"]) / 24) * 2 * np.pi)
                + (profile["weekday_bias"] if day < 5 else profile["weekend_bias"])
                + morning_peak
                + evening_peak
                + rng.normal(0, 850)
            )
            wind = profile["wind_base"] + profile["wind_amp"] * np.cos(((hour - shape["wind_peak_hour"]) / 24) * 2 * np.pi) + rng.normal(0, 400)
            solar_phase = (hour - shape["solar_rise_hour"]) / max(shape["solar_daylight_hours"], 1)
            solar = max(0, profile["solar_base"] * np.sin(solar_phase * np.pi)) + rng.normal(0, 140)
            precip = max(0, rng.normal(0.6, 0.7))
            scarcity = 1 if demand > (profile["demand_base"] + profile["demand_amp"] * 0.65) and wind < (profile["wind_base"] * 0.88) else 0
            basis = (
                42
                + 0.0012 * demand
                - 0.001 * wind
                - (0.00045 * shape["solar_price_discount"] * solar)
                + 0.15 * max(temp - 30, 0)
                + 18 * scarcity
            )
            basis += profile["regional_basis"]
            price = basis + rng.normal(0, 5.5 * shape["price_noise_scale"])

            db.add(
                PricePoint(
                    market_id=market.id,
                    timestamp=ts,
                    horizon_type="spot",
                    price_value=round(float(price), 2),
                    source=SYNTHETIC_SEED_SOURCE,
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
                    source=SYNTHETIC_SEED_SOURCE,
                )
            )
            db.add(
                DemandPoint(
                    market_id=market.id,
                    timestamp=ts,
                    demand_mw=round(float(max(25000, demand)), 2),
                    source=SYNTHETIC_SEED_SOURCE,
                )
            )

    db.flush()

    existing_articles = list(db.scalars(select(NewsArticle)).all())
    for payload in article_payloads:
        source_meta = NEWS_SOURCE_MAP[payload["source_key"]]
        existing_article = next(
            (
                article
                for article in existing_articles
                if (article.raw_json or {}).get("seed_key") == payload["seed_key"]
            ),
            None,
        )
        if existing_article is None:
            existing_article = db.scalar(select(NewsArticle).where(NewsArticle.title == payload["title"]))
        if existing_article is None and pair_counts[(payload["source_key"], payload["market_code"])] == 1:
            existing_article = next(
                (
                    article
                    for article in existing_articles
                    if (article.raw_json or {}).get("source_key") == payload["source_key"]
                    and (article.raw_json or {}).get("market_code") == payload["market_code"]
                ),
                None,
            )
        raw_json = {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in payload.items()
        }
        raw_json.update(
            {
                "source_url": payload.get("source_url", source_meta["url"]),
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
            article.title = payload["title"]
            article.source_name = source_meta["name"]
            article.source_url = payload.get("source_url", source_meta["url"])
            article.published_at = payload["published_at"]
            article.raw_json = raw_json
            article.processed_status = "processed"
        else:
            article = NewsArticle(
                title=payload["title"],
                body=payload["body"],
                source_name=source_meta["name"],
                source_url=payload.get("source_url", source_meta["url"]),
                published_at=payload["published_at"],
                raw_json=raw_json,
                processed_status="processed",
            )
            db.add(article)
            db.flush()
            existing_articles.append(article)

        market = market_map.get(payload["market_code"])
        extracted = extract_primary_event(payload["title"], payload["body"], market.region if market else "ERCOT")
        existing_event = db.scalar(select(Event).where(Event.article_id == article.id))
        if extracted:
            event_values = {
                "article_id": article.id,
                "market_id": market.id if market else None,
                "event_type": extracted.event_type,
                "title": extracted.title,
                "description": extracted.description,
                "affected_region": extracted.affected_region,
                "asset_type": extracted.asset_type,
                "capacity_impact_mw": extracted.capacity_impact_mw,
                "start_time": extracted.start_time,
                "expected_end_time": extracted.expected_end_time,
                "severity": extracted.severity,
                "confidence": extracted.confidence,
                "price_direction": extracted.price_direction,
                "estimated_price_impact_pct": estimate_price_impact_pct(extracted),
                "rationale": extracted.rationale,
            }
            if existing_event:
                for key, value in event_values.items():
                    setattr(existing_event, key, value)
            else:
                db.add(Event(**event_values))

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
