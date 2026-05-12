from __future__ import annotations

from app.services.portfolio_risk import PortfolioLegSpec, simulate_portfolio_from_leg_specs


def test_anti_correlated_positions_reduce_portfolio_risk() -> None:
    legs = [
        PortfolioLegSpec(
            market_code="A",
            position_gbp=10_000.0,
            direction="long",
            likely_gbp=0.0,
            sigma_return=0.05,
            standalone_risk_gbp=1030.0,
            standalone_upside_gbp=820.0,
        ),
        PortfolioLegSpec(
            market_code="B",
            position_gbp=10_000.0,
            direction="long",
            likely_gbp=0.0,
            sigma_return=0.05,
            standalone_risk_gbp=1030.0,
            standalone_upside_gbp=820.0,
        ),
    ]

    result = simulate_portfolio_from_leg_specs(
        legs,
        {"A": {"B": -0.8}, "B": {"A": -0.8}},
        n_paths=20_000,
        random_seed=9,
    )

    assert result["portfolio_risk_gbp"] < result["sum_standalone_risk_gbp"]
    assert len(result["contributions"]) == 2


def test_long_short_same_market_diversifies_portfolio_risk() -> None:
    legs = [
        PortfolioLegSpec(
            market_code="A",
            position_gbp=10_000.0,
            direction="long",
            likely_gbp=0.0,
            sigma_return=0.05,
            standalone_risk_gbp=1030.0,
            standalone_upside_gbp=820.0,
        ),
        PortfolioLegSpec(
            market_code="B",
            position_gbp=10_000.0,
            direction="short",
            likely_gbp=0.0,
            sigma_return=0.05,
            standalone_risk_gbp=1030.0,
            standalone_upside_gbp=820.0,
        ),
    ]

    hedged = simulate_portfolio_from_leg_specs(
        legs,
        {"A": {"B": 0.95}, "B": {"A": 0.95}},
        n_paths=20_000,
        random_seed=12,
    )
    uncorrelated = simulate_portfolio_from_leg_specs(
        legs,
        {"A": {"B": 0.0}, "B": {"A": 0.0}},
        n_paths=20_000,
        random_seed=12,
    )

    assert hedged["portfolio_risk_gbp"] < uncorrelated["portfolio_risk_gbp"]
