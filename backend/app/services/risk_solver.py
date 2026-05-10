from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.risk_engine import RiskInputs, assess_risk


SOLVER_ITERATIONS = 12
SOLVER_N_PATHS = 5_000
SOLVER_TOLERANCE_PCT = 0.02
SOLVER_SEED = 260510


@dataclass
class RiskSolveInputs:
    market_code: str
    max_risk_gbp: float
    horizon_hours: int
    direction: str
    position_unit: str = "GBP"
    target_timestamp: datetime | None = None


AssessmentFn = Callable[[Session | None, RiskInputs], dict[str, Any]]


def _resolved_request(inputs: RiskSolveInputs, position_gbp: float) -> dict[str, Any]:
    return {
        "market_code": inputs.market_code,
        "position_gbp": round(float(position_gbp), 2),
        "position_unit": inputs.position_unit,
        "position_mwh": None,
        "hedge_ratio": 1.0,
        "horizon_hours": int(inputs.horizon_hours),
        "direction": inputs.direction,
        "target_timestamp": inputs.target_timestamp,
        "scenarios": [],
        "n_paths": SOLVER_N_PATHS,
    }


def solve_position_for_risk(
    db: Session | None,
    inputs: RiskSolveInputs,
    *,
    assess_fn: AssessmentFn = assess_risk,
) -> dict[str, Any]:
    """Resolve a GBP notional whose simulated CVaR lands near max_risk_gbp."""
    if inputs.max_risk_gbp <= 0:
        raise ValueError("max_risk_gbp must be positive")
    if inputs.position_unit != "GBP":
        raise ValueError("risk-first sizing currently supports GBP notional positions")

    target = float(inputs.max_risk_gbp)
    tolerance_abs = max(0.01, target * SOLVER_TOLERANCE_PCT)

    def run(position_gbp: float) -> dict[str, Any]:
        return assess_fn(
            db,
            RiskInputs(
                market_code=inputs.market_code,
                position_gbp=max(float(position_gbp), 1e-6),
                position_unit=inputs.position_unit,
                position_mwh=None,
                hedge_ratio=1.0,
                horizon_hours=int(inputs.horizon_hours),
                target_timestamp=inputs.target_timestamp,
                direction=inputs.direction,
                n_paths=SOLVER_N_PATHS,
                scenarios=[],
                random_seed=SOLVER_SEED,
            ),
        )

    probe_position = max(1_000.0, target)
    probe = run(probe_position)
    probe_risk = float(probe["risk_gbp"])
    if probe_risk <= 0:
        raise ValueError("risk estimate is zero; cannot solve position size")

    low = 0.0
    high = max(1e-6, probe_position * target / probe_risk * 2.0)
    best_position = probe_position
    best_result = probe
    best_error = abs(probe_risk - target)
    converged = best_error <= tolerance_abs
    iterations = 0

    for iteration in range(1, SOLVER_ITERATIONS + 1):
        iterations = iteration
        candidate = (low + high) / 2.0
        result = run(candidate)
        risk = float(result["risk_gbp"])
        error = abs(risk - target)

        if error < best_error:
            best_position = candidate
            best_result = result
            best_error = error

        if error <= tolerance_abs:
            converged = True
            best_position = candidate
            best_result = result
            break

        if risk < target:
            low = candidate
        else:
            high = candidate

    achieved_risk = float(best_result["risk_gbp"])
    return {
        "max_risk_gbp": round(target, 2),
        "achieved_risk_gbp": round(achieved_risk, 2),
        "risk_error_pct": round(abs(achieved_risk - target) / target, 6),
        "tolerance_pct": SOLVER_TOLERANCE_PCT,
        "iterations": iterations,
        "converged": converged or abs(achieved_risk - target) <= tolerance_abs,
        "resolved_request": _resolved_request(inputs, best_position),
        "assessment": best_result,
    }
