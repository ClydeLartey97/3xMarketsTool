from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def latest_backtest_report_for_market(market_code: str) -> dict[str, Any] | None:
    candidates = sorted(REPORTS_DIR.glob(f"backtest_{market_code}_*.json"))
    for path in reversed(candidates):
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
    return None


def dashboard_backtest_metrics(market_code: str) -> dict[str, float]:
    report = latest_backtest_report_for_market(market_code)
    if report is None:
        return {
            "backtest_rmse_model": 0.0,
            "backtest_rmse_persistence_24h": 0.0,
            "backtest_calibrated": 0.0,
            "backtest_breach_rate_realized": 0.0,
        }

    calibration = report.get("calibration", {}) or {}
    pit_shares = calibration.get("shares", []) or []
    breach_rate = float(calibration.get("breach_rate_realized", 0.0) or 0.0)
    if breach_rate == 0.0 and pit_shares:
        breach_rate = float(pit_shares[0]) / 2.0

    return {
        "backtest_rmse_model": float((report.get("metrics", {}) or {}).get("rmse", 0.0) or 0.0),
        "backtest_rmse_persistence_24h": float(
            ((report.get("vs_baselines", {}) or {}).get("persistence_24h", {}) or {}).get("rmse", 0.0) or 0.0
        ),
        "backtest_calibrated": 1.0 if bool(calibration.get("well_calibrated", False)) else 0.0,
        "backtest_breach_rate_realized": round(float(breach_rate), 6),
    }
