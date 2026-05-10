from __future__ import annotations

from app.services.risk_engine import RiskInputs
from app.services.risk_solver import SOLVER_N_PATHS, RiskSolveInputs, solve_position_for_risk


def _linear_assessor(risk_per_gbp: float):
    def assess(_db, inputs: RiskInputs) -> dict:
        assert inputs.n_paths == SOLVER_N_PATHS
        return {
            "market_code": inputs.market_code,
            "position_gbp": inputs.position_gbp,
            "risk_gbp": round(inputs.position_gbp * risk_per_gbp, 2),
            "likely_gbp": round(inputs.position_gbp * 0.01, 2),
            "upside_gbp": round(inputs.position_gbp * 0.12, 2),
        }

    return assess


def test_position_solver_converges_with_known_sigma() -> None:
    known_sigma_risk = 0.08
    result = solve_position_for_risk(
        None,
        RiskSolveInputs(
            market_code="GB_POWER",
            max_risk_gbp=800.0,
            horizon_hours=24,
            direction="long",
            position_unit="GBP",
        ),
        assess_fn=_linear_assessor(known_sigma_risk),
    )

    assert result["converged"] is True
    assert result["risk_error_pct"] <= result["tolerance_pct"]
    assert result["assessment"]["risk_gbp"] == 800.0
    assert result["resolved_request"]["position_gbp"] == 10_000.0


def test_position_solver_is_monotonic_in_target_risk() -> None:
    assessor = _linear_assessor(0.05)
    smaller = solve_position_for_risk(
        None,
        RiskSolveInputs("GB_POWER", 500.0, 24, "long", "GBP"),
        assess_fn=assessor,
    )
    larger = solve_position_for_risk(
        None,
        RiskSolveInputs("GB_POWER", 1_000.0, 24, "long", "GBP"),
        assess_fn=assessor,
    )

    assert larger["resolved_request"]["position_gbp"] > smaller["resolved_request"]["position_gbp"]
    assert larger["assessment"]["risk_gbp"] > smaller["assessment"]["risk_gbp"]
