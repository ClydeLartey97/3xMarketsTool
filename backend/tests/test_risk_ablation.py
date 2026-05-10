from __future__ import annotations

import numpy as np

from app.services.risk_ablation import kupiec_pof_p_value, summarize_ablation_rows


def test_kupiec_pof_penalizes_bad_breach_rate() -> None:
    well_calibrated = kupiec_pof_p_value(50, 1000, claimed_probability=0.05)
    badly_calibrated = kupiec_pof_p_value(160, 1000, claimed_probability=0.05)

    assert well_calibrated > 0.95
    assert badly_calibrated < 0.001


def test_ablation_without_misspecified_llm_is_closer_to_claimed_breach_rate() -> None:
    rng = np.random.default_rng(42)
    realized = rng.normal(0.0, 100.0, size=1000)
    rows = [
        {
            "regime": "stressed" if index % 3 == 0 else "calm",
            "realized_pnl_gbp": float(pnl),
            "risk_gbp_with_llm": 80.0,
            "risk_gbp_without_llm": 164.5,
        }
        for index, pnl in enumerate(realized)
    ]

    summary = summarize_ablation_rows(rows)

    with_error = abs(summary["breach_rate_with_llm"] - 0.05)
    without_error = abs(summary["breach_rate_without_llm"] - 0.05)
    assert without_error < with_error
    assert summary["kupiec_p_value_without_llm"] > summary["kupiec_p_value_with_llm"]
    assert {"calm", "stressed"} <= set(summary["per_regime"])
