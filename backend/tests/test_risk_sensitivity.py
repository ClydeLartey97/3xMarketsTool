from __future__ import annotations

from app.services.risk_engine import RiskInputs
from app.services.risk_sensitivity import run_risk_sensitivity


def _tail_sensitive_assessor(_db, inputs: RiskInputs) -> dict:
    overrides = inputs.coefficient_overrides or {}
    tail = float(overrides.get("tail_multiplier", 1.0))
    risk = inputs.position_gbp * 0.10 * tail
    return {
        "risk_gbp": risk,
        "likely_gbp": inputs.position_gbp * 0.02,
        "upside_gbp": inputs.position_gbp * 0.18,
        "tail_multiplier": tail,
        "asymmetry": 0.2,
        "catalyst_severity": 0.4,
        "sigma_hourly_pct": 4.0,
        "fx_to_gbp": 1.0,
        "coefficients": {
            "items": [
                {"key": "drift_hourly_total", "value": 0.01},
                {"key": "hedge_ratio", "value": 1.0},
            ]
        },
    }


def test_sensitivity_tail_multiplier_is_monotonic() -> None:
    result = run_risk_sensitivity(
        None,
        RiskInputs(
            market_code="GB_POWER",
            position_gbp=10_000.0,
            horizon_hours=24,
            target_timestamp=None,
            direction="long",
        ),
        ["tail_multiplier"],
        assess_fn=_tail_sensitive_assessor,
    )

    row = result["rows"][0]
    risks = [cell["risk_gbp"] for cell in row["cells"]]
    baseline_index = result["perturbations_pct"].index(0.0)
    assert row["coefficient"] == "tail_multiplier"
    assert risks == sorted(risks)
    assert risks[0] < risks[baseline_index] < risks[-1]
