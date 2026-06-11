from types import SimpleNamespace

from app.ingestion.news_rss import _market_aliases, _match_market_for_article


def _market(code: str, name: str, region: str, metadata: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        code=code,
        name=name,
        region=region,
        metadata_json=metadata or {},
    )


def test_rss_market_matcher_recognises_european_power_aliases() -> None:
    markets = [
        _market("EPEX_DE", "EPEX Germany Day-Ahead", "Germany", {"nodes": ["EPEX_DE_LU"], "market_family": "EPEX"}),
        _market("EPEX_FR", "EPEX France Day-Ahead", "France", {"nodes": ["EPEX_FR"], "market_family": "EPEX"}),
        _market("NORDPOOL_SE3", "Nord Pool SE3", "Nordics", {"nodes": ["SE3"], "market_family": "Nord Pool"}),
    ]
    aliases = {market.code: (market, _market_aliases(market)) for market in markets}

    france = _match_market_for_article(
        aliases,
        "RTE outage tightens French day-ahead power",
        "French power traders are watching EPEX France liquidity and cross-border flows.",
    )
    nordic = _match_market_for_article(
        aliases,
        "Nord Pool SE3 prices rise as Sweden wind forecast slips",
        "Nordic power flow-based coupling leaves SE3 more exposed into the evening peak.",
    )

    assert france is markets[1]
    assert nordic is markets[2]


def test_rss_market_matcher_prefers_specific_hub_over_broad_region() -> None:
    markets = [
        _market("ERCOT_NORTH", "ERCOT North Hub", "Texas", {"nodes": ["HB_NORTH"]}),
        _market("ERCOT_HOUSTON", "ERCOT Houston Hub", "Texas", {"nodes": ["HB_HOUSTON"]}),
    ]
    aliases = {market.code: (market, _market_aliases(market)) for market in markets}

    matched = _match_market_for_article(
        aliases,
        "Transmission outage creates local constraint in Houston",
        "ERCOT Houston Hub imports are constrained while the wider Texas grid remains balanced.",
    )

    assert matched is markets[1]
