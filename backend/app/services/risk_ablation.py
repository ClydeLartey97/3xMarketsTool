from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Market, PricePoint
from app.services.risk_engine import RiskInputs, assess_risk


LLM_DISABLED_OVERRIDES = {
    "tail_multiplier": 1.0,
    "asymmetry": 0.0,
    "catalyst_severity": 0.0,
}


def kupiec_pof_p_value(breach_count: int, sample_count: int, claimed_probability: float = 0.05) -> float:
    if sample_count <= 0:
        return 1.0
    x = int(breach_count)
    n = int(sample_count)
    p = float(np.clip(claimed_probability, 1e-12, 1.0 - 1e-12))
    phat = float(np.clip(x / n, 1e-12, 1.0 - 1e-12))

    ll_null = (n - x) * math.log(1.0 - p) + x * math.log(p)
    ll_alt = (n - x) * math.log(1.0 - phat) + x * math.log(phat)
    lr_uc = max(0.0, -2.0 * (ll_null - ll_alt))
    return float(math.erfc(math.sqrt(lr_uc / 2.0)))


def _realized_pnl_gbp(current_price: float, next_price: float, position_gbp: float, direction: str) -> float:
    direction_sign = 1.0 if direction.lower() == "long" else -1.0
    reference = max(abs(float(current_price)), 1.0)
    return direction_sign * float(position_gbp) * ((float(next_price) - float(current_price)) / reference)


def summarize_ablation_rows(
    rows: list[dict[str, Any]],
    *,
    claimed_probability: float = 0.05,
    include_per_regime: bool = True,
) -> dict[str, Any]:
    sample_count = len(rows)
    if sample_count == 0:
        return {
            "breach_rate_with_llm": 0.0,
            "breach_rate_without_llm": 0.0,
            "kupiec_p_value_with_llm": 1.0,
            "kupiec_p_value_without_llm": 1.0,
            "sample_count": 0,
            "per_regime": {},
        }

    breach_with = np.array(
        [float(row["realized_pnl_gbp"]) <= -float(row["risk_gbp_with_llm"]) for row in rows],
        dtype=bool,
    )
    breach_without = np.array(
        [float(row["realized_pnl_gbp"]) <= -float(row["risk_gbp_without_llm"]) for row in rows],
        dtype=bool,
    )
    breach_count_with = int(breach_with.sum())
    breach_count_without = int(breach_without.sum())

    per_regime: dict[str, dict[str, Any]] = {}
    if include_per_regime:
        for regime in sorted({str(row.get("regime", "unknown")) for row in rows}):
            regime_rows = [row for row in rows if str(row.get("regime", "unknown")) == regime]
            regime_summary = summarize_ablation_rows(
                regime_rows,
                claimed_probability=claimed_probability,
                include_per_regime=False,
            )
            regime_summary.pop("per_regime", None)
            per_regime[regime] = regime_summary

    return {
        "breach_rate_with_llm": round(breach_count_with / sample_count, 6),
        "breach_rate_without_llm": round(breach_count_without / sample_count, 6),
        "kupiec_p_value_with_llm": round(kupiec_pof_p_value(breach_count_with, sample_count, claimed_probability), 6),
        "kupiec_p_value_without_llm": round(
            kupiec_pof_p_value(breach_count_without, sample_count, claimed_probability),
            6,
        ),
        "sample_count": sample_count,
        "per_regime": per_regime,
    }


def run_risk_ablation(
    market_code: str,
    lookback_days: int,
    position_gbp: float,
    *,
    direction: str = "long",
    horizon_hours: int = 1,
    n_paths: int = 1000,
    max_samples: int | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    if db is None:
        with SessionLocal() as session:
            return run_risk_ablation(
                market_code,
                lookback_days,
                position_gbp,
                direction=direction,
                horizon_hours=horizon_hours,
                n_paths=n_paths,
                max_samples=max_samples,
                db=session,
            )

    market = db.scalar(select(Market).where(Market.code == market_code))
    if market is None:
        raise ValueError(f"unknown market {market_code}")

    since = datetime.now(timezone.utc) - timedelta(days=int(lookback_days))
    prices = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id, PricePoint.timestamp >= since)
            .order_by(PricePoint.timestamp.asc())
        ).all()
    )
    pairs = [
        (current, nxt)
        for current, nxt in zip(prices, prices[1:])
        if (_as_utc(nxt.timestamp) - _as_utc(current.timestamp)).total_seconds() <= 2.5 * 3600
    ]
    if max_samples is not None and len(pairs) > max_samples:
        indices = np.linspace(0, len(pairs) - 1, int(max_samples), dtype=int)
        pairs = [pairs[int(index)] for index in indices]

    rows: list[dict[str, Any]] = []
    for index, (current, nxt) in enumerate(pairs):
        seed = 10_000 + index
        inputs = RiskInputs(
            market_code=market_code,
            position_gbp=float(position_gbp),
            horizon_hours=int(horizon_hours),
            target_timestamp=_as_utc(current.timestamp),
            direction=direction,
            n_paths=int(n_paths),
            random_seed=seed,
        )
        disabled_inputs = RiskInputs(
            market_code=market_code,
            position_gbp=float(position_gbp),
            horizon_hours=int(horizon_hours),
            target_timestamp=_as_utc(current.timestamp),
            direction=direction,
            n_paths=int(n_paths),
            random_seed=seed,
            coefficient_overrides=LLM_DISABLED_OVERRIDES,
        )
        try:
            with_llm = assess_risk(db, inputs)
            without_llm = assess_risk(db, disabled_inputs)
        except Exception:
            continue

        rows.append(
            {
                "timestamp": _as_utc(current.timestamp).isoformat(),
                "regime": str(with_llm.get("regime", "unknown")),
                "realized_pnl_gbp": _realized_pnl_gbp(
                    current.price_value,
                    nxt.price_value,
                    float(position_gbp),
                    direction,
                ),
                "risk_gbp_with_llm": float(with_llm["risk_gbp"]),
                "risk_gbp_without_llm": float(without_llm["risk_gbp"]),
            }
        )

    summary = summarize_ablation_rows(rows)
    summary.update(
        {
            "market_code": market.code,
            "market_name": market.name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_days": int(lookback_days),
            "position_gbp": float(position_gbp),
            "direction": direction,
            "horizon_hours": int(horizon_hours),
            "n_paths": int(n_paths),
        }
    )
    return summary


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
