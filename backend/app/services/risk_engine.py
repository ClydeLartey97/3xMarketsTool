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
from app.services.llm_scorer import ScoredArticle, score_news_context


# Standard normal inverse for one-sided 95% (z ≈ 1.6449)
_Z95 = 1.6449
# CVaR multiplier under normality at 95% (φ(z)/(1-α) ≈ 2.0627)
_CVAR95_MULT = 2.0627


@dataclass
class RiskInputs:
    market_code: str
    position_gbp: float
    horizon_hours: int
    target_timestamp: datetime | None  # if set, narrow assessment to that hour
    direction: str  # "long" or "short"


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

    # 4) Forecast-implied expected return
    # The forecast model already gives us point + lower/upper. Build an implied
    # distribution from the band, widen with LLM tail multiplier.
    point = float(chosen.point_estimate)
    fcst_lower = float(chosen.lower_bound)
    fcst_upper = float(chosen.upper_bound)
    half_band = max(point - fcst_lower, fcst_upper - point, max(spot * 0.02, 1.0))
    sigma_price = half_band / _Z95  # implied σ of price at horizon
    sigma_price *= float(context["tail_multiplier"])

    # Asymmetry shifts the mean (catalysts have a directional bias)
    drift = sigma_price * 0.35 * float(context["asymmetry"]) * float(context["catalyst_severity"])
    expected_price = point + drift

    # P&L per £1 long position over the horizon = (P_T - P_0) / P_0
    if spot <= 0:
        spot = max(point, 1.0)
    direction_sign = 1.0 if inputs.direction.lower() == "long" else -1.0
    expected_return_pct = direction_sign * (expected_price - spot) / spot
    sigma_return_pct = sigma_price / spot

    likely_pnl = inputs.position_gbp * expected_return_pct
    upside_pnl = inputs.position_gbp * (expected_return_pct + _Z95 * sigma_return_pct)
    # 95% CVaR: expected loss in the worst 5% (under near-normal assumption)
    var95_pnl = inputs.position_gbp * max(0.0, _Z95 * sigma_return_pct - expected_return_pct)
    cvar95_pnl = inputs.position_gbp * max(
        0.0, _CVAR95_MULT * sigma_return_pct - expected_return_pct
    )
    risk_pnl = cvar95_pnl  # the headline risk number

    # Edge score: compares expected return to risk on a normalised scale
    edge = 0.0
    if cvar95_pnl > 0:
        edge = float(np.clip(likely_pnl / cvar95_pnl, -2.0, 2.0))
    confidence = float(context["confidence"]) * float(model_metrics.get("directional_accuracy", 0.5) or 0.5)
    confidence = max(0.05, min(0.95, confidence))

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
        "sigma_price": round(sigma_price, 2),
        "sigma_hourly_pct": round(sigma_h * 100, 3),
        "expected_return_pct": round(expected_return_pct * 100, 3),
        "sigma_return_pct": round(sigma_return_pct * 100, 3),
        # The three headline numbers
        "risk_gbp": round(risk_pnl, 2),
        "likely_gbp": round(likely_pnl, 2),
        "upside_gbp": round(upside_pnl, 2),
        # Supporting numbers
        "var95_gbp": round(var95_pnl, 2),
        "edge_score": round(edge, 3),
        "confidence": round(confidence, 3),
        # LLM context surface
        "regime": context["regime"],
        "catalyst_severity": context["catalyst_severity"],
        "asymmetry": context["asymmetry"],
        "tail_multiplier": context["tail_multiplier"],
        "scorer_provider": context.get("provider", "heuristic"),
        "rationale": context["rationale"],
    }
