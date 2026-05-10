from __future__ import annotations

import json

from scripts.render_report import render_report


def test_render_report_contains_expected_sections(tmp_path) -> None:
    report_path = tmp_path / "sample_report.json"
    report_path.write_text(
        json.dumps(
            {
                "market_code": "GB_POWER",
                "generated_at": "2026-05-10T00:00:00Z",
                "sample_count": 100,
                "metrics": {"mae": 1.2, "rmse": 2.3, "directional_accuracy": 0.6},
                "vs_baselines": {"persistence": {"rmse": 3.4}},
                "vs_forecasters": {"gbr": {"rmse": 2.3}, "chronos": {"rmse": 2.1}},
                "metrics_by_hour": {"0": {"rmse": 1.0}, "1": {"rmse": 1.2}},
                "metrics_by_regime": {"calm": {"rmse": 1.1}},
                "calibration": {
                    "shares": [0.08, 0.1, 0.12, 0.09, 0.11, 0.1, 0.1, 0.09, 0.1, 0.11],
                    "expected_share_per_bin": 0.1,
                    "well_calibrated": True,
                },
                "llm_ablation": {
                    "breach_rate_with_llm": 0.07,
                    "breach_rate_without_llm": 0.05,
                    "kupiec_p_value_with_llm": 0.1,
                    "kupiec_p_value_without_llm": 0.9,
                    "per_regime": {"calm": {"breach_rate_with_llm": 0.04}},
                },
            }
        )
    )

    output = render_report(report_path)
    html = output.read_text()

    assert output == report_path.with_suffix(".html")
    assert "Headline Metrics" in html
    assert "Vs Baselines" in html
    assert "Vs Forecasters" in html
    assert "Hour-Of-Day Breakdown" in html
    assert "Regime Breakdown" in html
    assert "PIT Histogram" in html
    assert "LLM Ablation" in html
    assert "<svg" in html
