from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.services.correlation import get_correlation_matrix
from app.services.risk_engine import RiskInputs, assess_risk
from app.services.risk_simulator import empirical_risk_metrics


@dataclass
class PortfolioPositionInput:
    market_code: str
    position_gbp: float
    direction: str = "long"


@dataclass
class PortfolioLegSpec:
    market_code: str
    position_gbp: float
    direction: str
    likely_gbp: float
    sigma_return: float
    standalone_risk_gbp: float
    standalone_upside_gbp: float


def run_portfolio_risk(
    db: Session,
    positions: list[PortfolioPositionInput],
    *,
    horizon_hours: int = 24,
    n_paths: int = 5000,
    random_seed: int | None = None,
) -> dict[str, Any]:
    if not positions:
        raise ValueError("portfolio requires at least one position")

    legs: list[PortfolioLegSpec] = []
    for index, position in enumerate(positions):
        assessment = assess_risk(
            db,
            RiskInputs(
                market_code=position.market_code,
                position_gbp=float(position.position_gbp),
                horizon_hours=int(horizon_hours),
                target_timestamp=None,
                direction=position.direction,
                n_paths=max(500, min(int(n_paths), 20_000)),
                random_seed=(random_seed + index + 1) if random_seed is not None else None,
            ),
        )
        sigma_return = max(
            float(assessment.get("sigma_return_pct", 0.0) or 0.0) / 100.0,
            float(assessment["risk_gbp"]) / max(float(position.position_gbp) * 2.0627, 1.0),
            1e-6,
        )
        legs.append(
            PortfolioLegSpec(
                market_code=position.market_code,
                position_gbp=float(position.position_gbp),
                direction=position.direction,
                likely_gbp=float(assessment["likely_gbp"]),
                sigma_return=sigma_return,
                standalone_risk_gbp=float(assessment["risk_gbp"]),
                standalone_upside_gbp=float(assessment["upside_gbp"]),
            )
        )

    correlation_matrix = get_correlation_matrix(db)
    result = simulate_portfolio_from_leg_specs(
        legs,
        correlation_matrix,
        n_paths=n_paths,
        random_seed=random_seed,
    )
    result.update(
        {
            "horizon_hours": int(horizon_hours),
            "n_paths": int(n_paths),
            "correlation_source": "hourly_returns_6h_cache",
        }
    )
    return result


def simulate_portfolio_from_leg_specs(
    legs: list[PortfolioLegSpec],
    correlation_matrix: dict[str, dict[str, float]],
    *,
    n_paths: int = 5000,
    random_seed: int | None = None,
) -> dict[str, Any]:
    if not legs:
        raise ValueError("portfolio requires at least one position")

    rng = np.random.default_rng(random_seed)
    corr = _pnl_correlation_matrix(legs, correlation_matrix)
    shocks = rng.multivariate_normal(np.zeros(len(legs)), corr, size=max(1, int(n_paths)))
    pnl_columns: list[np.ndarray] = []
    for index, leg in enumerate(legs):
        # `corr` is already a P&L correlation matrix, with long/short signs
        # applied in `_pnl_correlation_matrix`. Applying direction again here
        # would erase diversification for opposite positions.
        pnl = leg.likely_gbp + leg.position_gbp * leg.sigma_return * shocks[:, index]
        pnl_columns.append(pnl)

    pnl_matrix = np.column_stack(pnl_columns)
    portfolio_pnl = pnl_matrix.sum(axis=1)
    metrics = empirical_risk_metrics(portfolio_pnl)
    var_floor = np.percentile(portfolio_pnl, 5)
    tail_mask = portfolio_pnl <= var_floor
    contribution_basis = np.abs(pnl_matrix[tail_mask].mean(axis=0)) if tail_mask.any() else np.zeros(len(legs))
    basis_sum = float(contribution_basis.sum())

    contributions: list[dict[str, Any]] = []
    for index, leg in enumerate(legs):
        risk_contribution = (
            metrics["cvar95_gbp"] * float(contribution_basis[index]) / basis_sum
            if basis_sum > 0
            else metrics["cvar95_gbp"] / len(legs)
        )
        leg_metrics = empirical_risk_metrics(pnl_matrix[:, index])
        contributions.append(
            {
                "market_code": leg.market_code,
                "position_gbp": round(leg.position_gbp, 2),
                "direction": leg.direction,
                "standalone_risk_gbp": round(leg.standalone_risk_gbp, 2),
                "standalone_likely_gbp": round(leg.likely_gbp, 2),
                "standalone_upside_gbp": round(leg.standalone_upside_gbp, 2),
                "simulated_risk_gbp": round(leg_metrics["cvar95_gbp"], 2),
                "risk_contribution_gbp": round(float(risk_contribution), 2),
            }
        )

    return {
        "portfolio_risk_gbp": round(metrics["cvar95_gbp"], 2),
        "portfolio_likely_gbp": round(metrics["likely_gbp"], 2),
        "portfolio_upside_gbp": round(metrics["upside_gbp"], 2),
        "var95_gbp": round(metrics["var95_gbp"], 2),
        "prob_loss": round(metrics["prob_loss"], 4),
        "sum_standalone_risk_gbp": round(sum(leg.standalone_risk_gbp for leg in legs), 2),
        "contributions": contributions,
    }


def _pnl_correlation_matrix(
    legs: list[PortfolioLegSpec],
    correlation_matrix: dict[str, dict[str, float]],
) -> np.ndarray:
    n = len(legs)
    corr = np.eye(n, dtype=float)
    for i, left in enumerate(legs):
        left_sign = 1.0 if left.direction.lower() == "long" else -1.0
        for j, right in enumerate(legs):
            if i == j:
                continue
            right_sign = 1.0 if right.direction.lower() == "long" else -1.0
            market_corr = float(correlation_matrix.get(left.market_code, {}).get(right.market_code, 0.0))
            corr[i, j] = float(np.clip(market_corr * left_sign * right_sign, -0.99, 0.99))
    return _nearest_correlation_matrix(corr)


def _nearest_correlation_matrix(matrix: np.ndarray) -> np.ndarray:
    symmetric = (matrix + matrix.T) / 2.0
    eigvals, eigvecs = np.linalg.eigh(symmetric)
    clipped = np.clip(eigvals, 1e-6, None)
    psd = eigvecs @ np.diag(clipped) @ eigvecs.T
    scale = np.sqrt(np.clip(np.diag(psd), 1e-12, None))
    normalized = psd / np.outer(scale, scale)
    np.fill_diagonal(normalized, 1.0)
    return normalized
