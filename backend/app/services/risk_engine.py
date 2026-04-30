"""
Risk-assessment engine.

Produces three numbers for a position in a given market:

  - risk        : capital at risk (£), defined as 95% CVaR over the horizon
  - likely      : expected P&L (£), forecast distribution mean × position
  - upside      : 95th-percentile P&L (£), the realistic upside tail

The numbers are conditioned on:
  - quant features: realised volatility, forecast distribution,
                    intra-horizon variance scaling, regime classification
  - LLM features: catalyst severity, directional asymmetry, tail multiplier
                  (see services/llm_scorer.py)

This is the part that's the product's edge: the combination of the
forecast distribution + LLM-conditioned tail modelling means two markets
with the same point forecast can have very different risk reads when one
has loaded news flow and the other doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Forecast, Market, NewsArticle, PricePoint
from app.services.forecast_service import run_forecast_for_market
from app.services.fx import fx_to_gbp
from app.services.llm_scorer import ScoredArticle, score_news_context
from app.services.risk_simulator import (
    SimConfig,
    empirical_max_drawdown,
    empirical_risk_metrics,
    pnl_from_paths,
    simulate_price_paths,
)


# Standard normal inverse for one-sided 95% (z ≈ 1.6449)
_Z95 = 1.6449
# CVaR multiplier under normality at 95% (φ(z)/(1-α) ≈ 2.0627)
_CVAR95_NORMAL = 2.0627
# CVaR multiplier under Student-t with 5 dof at α=0.95
# E[T | T > t_{0.95}] / σ ≈ 2.73 for t(5)
_CVAR95_T5 = 2.73


def _cvar95_multiplier(tail_multiplier: float) -> float:
    """Blend Gaussian and t(5) CVaR multipliers based on the LLM tail read.

    When the LLM signals a tail-heavy regime (tail_multiplier > 1.2) the
    Gaussian closed-form understates CVaR. We linearly interpolate toward a
    t(5) approximation as the multiplier grows, fully transitioning by 2.0.
    """
    if tail_multiplier <= 1.2:
        return _CVAR95_NORMAL
    weight = min(1.0, (tail_multiplier - 1.2) / 0.8)
    return (1.0 - weight) * _CVAR95_NORMAL + weight * _CVAR95_T5


@dataclass
class ScenarioSpec:
    name: str
    sigma_multiplier: float = 1.0
    drift_shift: float = 0.0
    spot_shock_pct: float = 0.0


@dataclass
class RiskInputs:
    market_code: str
    position_gbp: float
    horizon_hours: int
    target_timestamp: datetime | None  # if set, narrow assessment to that hour
    direction: str  # "long" or "short"
    position_unit: str = "GBP"          # "GBP" (notional) or "MWh"
    position_mwh: float | None = None
    hedge_ratio: float = 1.0
    n_paths: int = 5000
    scenarios: list[ScenarioSpec] | None = None


# Canonical scenarios — keyed by name. Each one specifies a multiplicative
# σ shift, an additive log-return drift per hour, and an instantaneous spot
# shock (% of spot at t=0). The risk engine maps these to the simulator.
PRESET_SCENARIOS: dict[str, ScenarioSpec] = {
    "wind_drop_30pct":  ScenarioSpec("wind_drop_30pct",  sigma_multiplier=1.25, drift_shift=+0.0040, spot_shock_pct=+0.04),
    "outage_2gw":       ScenarioSpec("outage_2gw",       sigma_multiplier=1.40, drift_shift=+0.0080, spot_shock_pct=+0.08),
    "heatwave_+5C":     ScenarioSpec("heatwave_+5C",     sigma_multiplier=1.30, drift_shift=+0.0060, spot_shock_pct=+0.05),
    "gas_spike_+50pct": ScenarioSpec("gas_spike_+50pct", sigma_multiplier=1.20, drift_shift=+0.0100, spot_shock_pct=+0.10),
}


def _resolve_scenario(spec: ScenarioSpec) -> ScenarioSpec:
    """If `spec.name` matches a preset, use the preset; else use spec verbatim."""
    return PRESET_SCENARIOS.get(spec.name, spec)


def _recent_returns(prices: list[PricePoint], window: int = 168) -> np.ndarray:
    if len(prices) < 4:
        return np.array([])
    values = np.array([p.price_value for p in prices[-window:]], dtype=float)
    if (values <= 0).any():
        # power prices can technically go negative; fall back to absolute returns
        diffs = np.diff(values)
        ref = np.maximum(np.abs(values[:-1]), 1.0)
        return diffs / ref
    return np.diff(np.log(values))


def _hourly_vol(returns: np.ndarray) -> float:
    if returns.size < 6:
        return 0.06  # fallback, ~6% hourly std typical for power
    # Robust std via MAD-style scaling
    centered = returns - np.median(returns)
    mad = np.median(np.abs(centered))
    sigma = max(float(mad * 1.4826), float(np.std(returns, ddof=0)))
    return max(0.005, min(0.6, sigma))


def _select_forecast(forecasts: list[Forecast], target: datetime | None, horizon_hours: int) -> Forecast | None:
    if not forecasts:
        return None
    if target is None:
        # default to the last point inside the horizon
        bound = min(horizon_hours, len(forecasts)) - 1
        return forecasts[max(0, bound)]
    # find nearest forecast timestamp
    target_utc = target.astimezone(timezone.utc) if target.tzinfo else target.replace(tzinfo=timezone.utc)
    return min(
        forecasts[: max(1, horizon_hours)],
        key=lambda f: abs((_as_utc(f.forecast_for_timestamp) - target_utc).total_seconds()),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_scored_articles(news: list[NewsArticle]) -> list[ScoredArticle]:
    out: list[ScoredArticle] = []
    for article in news[:20]:
        raw = article.raw_json or {}
        published = _as_utc(article.published_at)
        out.append(
            ScoredArticle(
                title=str(raw.get("translated_title") or article.title),
                summary=str(raw.get("translated_summary") or raw.get("summary") or article.body[:280] or ""),
                source=article.source_name,
                published_at=published,
                credibility=float(raw.get("credibility_rating") or 70.0),
            )
        )
    return out


def _recent_market_articles(db: Session, market: Market, limit: int = 20) -> list[NewsArticle]:
    articles = list(
        db.scalars(
            select(NewsArticle)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit * 4)
        ).all()
    )
    if not articles:
        return []

    article_ids = [article.id for article in articles]
    events_by_article = {
        event.article_id: event
        for event in db.scalars(select(Event).where(Event.article_id.in_(article_ids)))
        if event.article_id is not None
    }

    selected: list[NewsArticle] = []
    for article in articles:
        raw = article.raw_json or {}
        event = events_by_article.get(article.id)
        raw_market_code = raw.get("market_code")
        if event and event.market_id == market.id:
            selected.append(article)
        elif event and event.market_id is None and not raw_market_code:
            selected.append(article)
        elif raw_market_code == market.code:
            selected.append(article)
        elif not event and not raw_market_code:
            selected.append(article)
        if len(selected) >= limit:
            break
    return selected


def _events_summary(events: list[Event]) -> list[dict[str, Any]]:
    return [
        {
            "event_type": e.event_type,
            "severity": e.severity,
            "affected_region": e.affected_region,
            "title": e.title,
        }
        for e in events[:10]
    ]


def assess_risk(db: Session, inputs: RiskInputs) -> dict[str, Any]:
    market = db.scalar(select(Market).where(Market.code == inputs.market_code))
    if not market:
        raise ValueError(f"unknown market {inputs.market_code}")

    # 1) Forecast distribution
    forecasts, model_metrics = run_forecast_for_market(
        db, market, horizon_hours=max(inputs.horizon_hours, 24), use_cache=True
    )
    chosen = _select_forecast(forecasts, inputs.target_timestamp, inputs.horizon_hours)
    if not chosen:
        raise ValueError("no forecast available for this market")

    # 2) Realised vol from price history
    prices = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id)
            .order_by(PricePoint.timestamp.asc())
        ).all()
    )
    spot = prices[-1].price_value if prices else chosen.point_estimate
    returns = _recent_returns(prices)
    sigma_h = _hourly_vol(returns)
    sigma_horizon = sigma_h * np.sqrt(max(1.0, inputs.horizon_hours))

    # 3) LLM-conditioned context
    news = _recent_market_articles(db, market)
    events = list(
        db.scalars(
            select(Event)
            .where(Event.market_id == market.id)
            .order_by(Event.created_at.desc())
            .limit(10)
        ).all()
    )
    context = score_news_context(
        market_code=market.code,
        market_name=market.name,
        region=market.region,
        articles=_build_scored_articles(news),
        events_summary=_events_summary(events),
    )

    # 4) Build the price-distribution σ for the horizon
    # Source 1 — model-implied σ from the forecast snapshot.
    point = float(chosen.point_estimate)
    fcst_lower = float(chosen.lower_bound)
    fcst_upper = float(chosen.upper_bound)
    snapshot = chosen.feature_snapshot_json or {}
    snapshot_sigma = snapshot.get("sigma_price")
    if snapshot_sigma is not None:
        sigma_model = float(snapshot_sigma)
    else:
        half_band = max(point - fcst_lower, fcst_upper - point, max(spot * 0.02, 1.0))
        sigma_model = half_band / _Z95

    if spot <= 0:
        spot = max(point, 1.0)

    # Source 2 — realised σ from recent prices, scaled to the horizon.
    sigma_realised_price = sigma_h * np.sqrt(max(1.0, inputs.horizon_hours)) * spot

    # Sample-size-weighted blend, tail multiplier baked into the simulator
    # call below (not into σ here — keeps the units clean).
    n_obs = float(returns.size)
    w_realised = min(1.0, n_obs / 168.0)
    sigma_price_horizon = (1.0 - w_realised) * sigma_model + w_realised * sigma_realised_price

    # Convert horizon-σ in price units → hourly σ in log-return space, which
    # is what the simulator expects.
    sigma_hourly = (sigma_price_horizon / spot) / np.sqrt(max(1.0, inputs.horizon_hours))

    # Drift in log-return space. Forecast point already encodes the model
    # drift; pull (forecast - spot) into a per-hour log return, then add the
    # LLM asymmetry × catalyst nudge.
    horizon_log_return = float(np.log(max(point, 1e-6) / max(spot, 1e-6)))
    drift_hourly_base = horizon_log_return / max(1.0, inputs.horizon_hours)
    asym_drift = 0.05 * sigma_hourly * float(context["asymmetry"]) * float(context["catalyst_severity"])
    drift_hourly = drift_hourly_base + asym_drift

    direction_sign = 1.0 if inputs.direction.lower() == "long" else -1.0

    # Position resolution + FX. Each market's prices are stored in their
    # native currency (Phase 2.1); convert to GBP at the end.
    price_currency = (getattr(prices[-1], "currency", None) if prices else None) or "USD"
    fx = fx_to_gbp(price_currency)

    if inputs.position_unit == "MWh":
        position_native = float(inputs.position_mwh or 0.0) * float(inputs.hedge_ratio)
    else:
        # Interpret position_gbp as a GBP-denominated notional. Convert into
        # native price-currency notional for the simulator.
        position_native = (inputs.position_gbp / max(fx, 1e-6)) * float(inputs.hedge_ratio)

    base_cfg = SimConfig(
        n_paths=int(inputs.n_paths),
        horizon_hours=int(inputs.horizon_hours),
        spot=float(spot),
        sigma_hourly=float(sigma_hourly),
        drift_hourly=float(drift_hourly),
        tail_multiplier=float(context["tail_multiplier"]),
        asymmetry=float(context["asymmetry"]),
        seed=None,
    )

    base_result = simulate_price_paths(base_cfg)
    base_pnl_native = pnl_from_paths(
        base_result,
        direction_sign=direction_sign,
        position_native=position_native,
        position_unit=inputs.position_unit,
    )
    base_pnl_gbp = base_pnl_native * fx
    metrics = empirical_risk_metrics(base_pnl_gbp)

    risk_pnl = metrics["cvar95_gbp"]
    likely_pnl = metrics["likely_gbp"]
    upside_pnl = metrics["upside_gbp"]
    var95_pnl = metrics["var95_gbp"]
    prob_loss = metrics["prob_loss"]

    max_dd_gbp = empirical_max_drawdown(
        base_result,
        direction_sign=direction_sign,
        position_native=position_native,
        position_unit=inputs.position_unit,
        fx_to_gbp=fx,
    )

    risk_metric = "cvar_95_t5" if float(context["tail_multiplier"]) > 1.2 else "cvar_95_normal"

    # Scenario sweeps
    scenario_outcomes: list[dict[str, Any]] = []
    for spec in (inputs.scenarios or []):
        scenario = _resolve_scenario(spec)
        shocked_spot = max(1e-6, spot * (1.0 + scenario.spot_shock_pct))
        scen_cfg = SimConfig(
            n_paths=int(inputs.n_paths),
            horizon_hours=int(inputs.horizon_hours),
            spot=shocked_spot,
            sigma_hourly=float(sigma_hourly * scenario.sigma_multiplier),
            drift_hourly=float(drift_hourly + scenario.drift_shift),
            tail_multiplier=float(context["tail_multiplier"]),
            asymmetry=float(context["asymmetry"]),
            seed=None,
        )
        scen_result = simulate_price_paths(scen_cfg)
        scen_pnl_native = pnl_from_paths(
            scen_result,
            direction_sign=direction_sign,
            position_native=position_native,
            position_unit=inputs.position_unit,
        )
        scen_pnl_gbp = scen_pnl_native * fx
        scen_metrics = empirical_risk_metrics(scen_pnl_gbp)
        scenario_outcomes.append({
            "name": scenario.name,
            "risk_gbp": round(scen_metrics["cvar95_gbp"], 2),
            "likely_gbp": round(scen_metrics["likely_gbp"], 2),
            "upside_gbp": round(scen_metrics["upside_gbp"], 2),
            "prob_loss": round(scen_metrics["prob_loss"], 4),
        })

    # Edge & confidence
    edge = 0.0
    if risk_pnl > 0:
        edge = float(np.clip(likely_pnl / risk_pnl, -2.0, 2.0))
    confidence = float(context["confidence"]) * float(model_metrics.get("directional_accuracy", 0.5) or 0.5)
    confidence = max(0.05, min(0.95, confidence))

    expected_price = float(np.mean(base_result.terminal_prices))
    expected_return_pct = direction_sign * (expected_price - spot) / spot
    sigma_return_pct = sigma_hourly * np.sqrt(max(1.0, inputs.horizon_hours))

    return {
        "market_code": market.code,
        "market_name": market.name,
        "as_of": datetime.now(timezone.utc),
        "position_gbp": inputs.position_gbp,
        "direction": inputs.direction,
        "horizon_hours": inputs.horizon_hours,
        "target_timestamp": chosen.forecast_for_timestamp,
        "spot_price": round(spot, 2),
        "forecast_price": round(point, 2),
        "expected_price": round(expected_price, 2),
        "sigma_price": round(sigma_price_horizon, 2),
        "sigma_hourly_pct": round(sigma_hourly * 100, 3),
        "expected_return_pct": round(expected_return_pct * 100, 3),
        "sigma_return_pct": round(sigma_return_pct * 100, 3),
        # The three headline numbers — empirical from MC paths
        "risk_gbp": round(risk_pnl, 2),
        "likely_gbp": round(likely_pnl, 2),
        "upside_gbp": round(upside_pnl, 2),
        "risk_metric": risk_metric,
        # Supporting numbers
        "var95_gbp": round(var95_pnl, 2),
        "prob_loss": round(prob_loss, 4),
        "max_drawdown_gbp": round(max_dd_gbp, 2),
        "fx_to_gbp": round(fx, 6),
        "price_currency": price_currency,
        "n_paths": int(inputs.n_paths),
        "edge_score": round(edge, 3),
        "confidence": round(confidence, 3),
        "regime": context["regime"],
        "catalyst_severity": context["catalyst_severity"],
        "asymmetry": context["asymmetry"],
        "tail_multiplier": context["tail_multiplier"],
        "scorer_provider": context.get("provider", "heuristic"),
        "rationale": context["rationale"],
        "scenarios": scenario_outcomes,
    }
