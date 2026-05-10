from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.services.risk_engine import RiskInputs, assess_risk


SENSITIVITY_COEFFICIENTS = (
    "tail_multiplier",
    "asymmetry",
    "catalyst_severity",
    "sigma_hourly",
    "drift_hourly",
    "fx_to_gbp",
    "hedge_ratio",
)
SENSITIVITY_PERTURBATIONS = (-0.50, -0.25, 0.0, 0.25, 0.50)
SENSITIVITY_SEED = 260511

AssessmentFn = Callable[[Session | None, RiskInputs], dict[str, Any]]


def _coefficient_map(result: dict[str, Any]) -> dict[str, float]:
    items = {
        str(item.get("key")): float(item.get("value"))
        for item in (result.get("coefficients", {}).get("items") or [])
        if isinstance(item.get("value"), (int, float))
    }
    return {
        "tail_multiplier": float(result["tail_multiplier"]),
        "asymmetry": float(result["asymmetry"]),
        "catalyst_severity": float(result["catalyst_severity"]),
        "sigma_hourly": float(result["sigma_hourly_pct"]) / 100.0,
        "drift_hourly": float(items.get("drift_hourly_total", 0.0)),
        "fx_to_gbp": float(result["fx_to_gbp"]),
        "hedge_ratio": float(items.get("hedge_ratio", 1.0)),
    }


def _perturbed_value(coefficient: str, base_value: float, perturbation: float) -> float:
    value = float(base_value) * (1.0 + float(perturbation))
    if coefficient in {"sigma_hourly", "fx_to_gbp", "hedge_ratio", "tail_multiplier", "catalyst_severity"}:
        value = max(0.0, value)
    if coefficient == "hedge_ratio":
        value = min(1.0, value)
    return value


def run_risk_sensitivity(
    db: Session | None,
    base_inputs: RiskInputs,
    coefficients_to_perturb: list[str],
    *,
    assess_fn: AssessmentFn = assess_risk,
) -> dict[str, Any]:
    coefficients = coefficients_to_perturb or list(SENSITIVITY_COEFFICIENTS)
    unknown = sorted(set(coefficients) - set(SENSITIVITY_COEFFICIENTS))
    if unknown:
        raise ValueError(f"unsupported sensitivity coefficient(s): {', '.join(unknown)}")

    seeded_inputs = replace(base_inputs, random_seed=SENSITIVITY_SEED, coefficient_overrides={})
    baseline = assess_fn(db, seeded_inputs)
    base_values = _coefficient_map(baseline)

    rows: list[dict[str, Any]] = []
    for coefficient in coefficients:
        base_value = base_values[coefficient]
        cells: list[dict[str, float]] = []
        for perturbation in SENSITIVITY_PERTURBATIONS:
            overrides = {
                coefficient: _perturbed_value(coefficient, base_value, perturbation),
            }
            if perturbation == 0.0:
                result = baseline
            else:
                result = assess_fn(
                    db,
                    replace(
                        seeded_inputs,
                        coefficient_overrides=overrides,
                    ),
                )
            cells.append(
                {
                    "perturbation_pct": round(perturbation * 100.0, 1),
                    "risk_gbp": round(float(result["risk_gbp"]), 2),
                    "likely_gbp": round(float(result["likely_gbp"]), 2),
                    "upside_gbp": round(float(result["upside_gbp"]), 2),
                }
            )
        rows.append(
            {
                "coefficient": coefficient,
                "base_value": round(float(base_value), 8),
                "cells": cells,
            }
        )

    return {
        "market_code": base_inputs.market_code,
        "position_gbp": round(float(base_inputs.position_gbp), 2),
        "direction": base_inputs.direction,
        "horizon_hours": int(base_inputs.horizon_hours),
        "perturbations_pct": [round(p * 100.0, 1) for p in SENSITIVITY_PERTURBATIONS],
        "rows": rows,
    }
