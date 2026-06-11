import logging
import math
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.rate_limit import RISK_ASSESSMENT_LIMIT, SENSITIVITY_LIMIT, limiter
from app.models import DemandPoint, Event, Forecast, PricePoint, User, WeatherPoint
from app.schemas.domain import (
    AlertRead,
    ArticleIngestRequest,
    AuditLogRead,
    DashboardResponse,
    DashboardSummaryResponse,
    DecisionCreateRequest,
    DecisionRead,
    DecisionUpdateRequest,
    EventRead,
    ForecastRunResponse,
    ForecastRead,
    HealthResponse,
    MarketOverviewItem,
    MarketRead,
    MarketTimeseriesPoint,
    NewsArticleRead,
    NewsSourceRead,
    OptimalHedgeResponse,
    PortfolioRiskRequest,
    PortfolioRiskResponse,
    PowerBIEmbedConfig,
    PricePointRead,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskCalibrationResponse,
    RiskPathFanResponse,
    RiskSensitivityRequest,
    RiskSensitivityResponse,
    RiskSolveRequest,
    RiskSolveResponse,
)
from app.services.auth import audit_user, current_user
from app.services.audit import list_audit_logs, write_audit_log
from app.services.decision_diary import create_decision, delete_decision, list_decisions, update_decision
from app.services.risk_calibration import log_risk_assessment, risk_calibration_for_market
from app.services.event_analogues import find_analogues
from app.services.market_service import (
    build_markets_overview,
    get_market_by_code,
    get_market_by_id,
    list_markets,
    market_overview_to_dict,
)

logger = logging.getLogger(__name__)
public_router = APIRouter()
router = APIRouter(dependencies=[Depends(current_user)])
_DATA_REFRESH_LOCK = Lock()
_DATA_REFRESH_DUE_AFTER: datetime | None = None
_DATA_REFRESH_RUNNING = False


def _should_schedule_data_refresh() -> bool:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.environment.lower() not in {"production", "prod"}:
        return False

    interval_minutes = max(15, int(settings.data_refresh_interval_minutes or 30))
    now = datetime.now(timezone.utc)

    global _DATA_REFRESH_DUE_AFTER, _DATA_REFRESH_RUNNING
    with _DATA_REFRESH_LOCK:
        if _DATA_REFRESH_RUNNING:
            return False
        if _DATA_REFRESH_DUE_AFTER and now < _DATA_REFRESH_DUE_AFTER:
            return False
        _DATA_REFRESH_RUNNING = True
        _DATA_REFRESH_DUE_AFTER = now + timedelta(minutes=interval_minutes)
        return True


def _refresh_data_from_health_ping() -> None:
    from app.workers.jobs import refresh_all_markets

    global _DATA_REFRESH_RUNNING
    try:
        result = refresh_all_markets()
        logger.info("Health-triggered data refresh complete: %s", result)
    except Exception as exc:  # noqa: BLE001 - health-triggered refresh must never break health checks
        logger.warning("Health-triggered data refresh failed: %s", exc)
    finally:
        with _DATA_REFRESH_LOCK:
            _DATA_REFRESH_RUNNING = False


def _schedule_data_refresh(background_tasks: BackgroundTasks) -> None:
    if _should_schedule_data_refresh():
        background_tasks.add_task(_refresh_data_from_health_ping)


def _market_data_status(market) -> str:
    return (market.metadata_json or {}).get("data_status", "ready")


def _market_read(market) -> MarketRead:
    return MarketRead(
        id=market.id,
        name=market.name,
        code=market.code,
        commodity_type=market.commodity_type,
        region=market.region,
        timezone=market.timezone,
        data_status=_market_data_status(market),
        metadata=market.metadata_json,
    )


def _actor(user: User) -> str:
    return f"user:{user.id}:{user.email}"


def _audit_read(row) -> AuditLogRead:
    return AuditLogRead(
        id=row.id,
        created_at=row.created_at,
        actor=row.actor,
        action=row.action,
        target=row.target,
        before=row.before_json,
        after=row.after_json,
        signed_hash=row.signed_hash,
    )


def _price_ts(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_synthetic_price_source(source: str) -> bool:
    normalized = (source or "").lower()
    return normalized in {"computed", "computed-fundamentals", "synthetic"} or normalized.startswith("synthetic")


def _price_provenance_metrics(prices: list) -> dict[str, float]:
    if not prices:
        return {"data_freshness_minutes": 0.0, "synthetic_share_24h": 1.0}
    now = datetime.now(timezone.utc)
    latest_ts = max(_price_ts(point.timestamp) for point in prices)
    freshness_minutes = max(0.0, (now - latest_ts).total_seconds() / 60.0)
    cutoff = now - timedelta(hours=24)
    recent = [point for point in prices if _price_ts(point.timestamp) >= cutoff]
    if not recent:
        synthetic_share = 1.0
    else:
        synthetic_share = sum(1 for point in recent if _is_synthetic_price_source(point.source)) / len(recent)
    return {
        "data_freshness_minutes": round(float(freshness_minutes), 2),
        "synthetic_share_24h": round(float(synthetic_share), 4),
    }


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    return value


def _forecast_read(item: Forecast) -> ForecastRead:
    point = _finite_float(item.point_estimate)
    lower = _finite_float(item.lower_bound, point)
    upper = _finite_float(item.upper_bound, point)
    if lower > upper:
        lower, upper = upper, lower
    return ForecastRead(
        id=item.id,
        market_id=item.market_id,
        forecast_for_timestamp=item.forecast_for_timestamp,
        generated_at=item.generated_at,
        point_estimate=point,
        lower_bound=lower,
        upper_bound=upper,
        currency=item.currency or "USD",
        spike_probability=max(0.0, min(1.0, _finite_float(item.spike_probability))),
        model_version=item.model_version,
        rationale_summary=item.rationale_summary,
        feature_snapshot_json=_json_safe(item.feature_snapshot_json or {}),
    )


def _safe_json_response(payload: Any) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(_json_safe(payload)))


def _mean_finite(values: list[Any], default: float = 0.0) -> float:
    finite = [_finite_float(value) for value in values if math.isfinite(_finite_float(value, float("nan")))]
    if not finite:
        return default
    return sum(finite) / len(finite)


def _fallback_risk_assessment(
    db: Session,
    payload: RiskAssessmentRequest,
    *,
    reason: str,
) -> RiskAssessmentResponse:
    market = get_market_by_code(db, payload.market_code)
    if not market:
        raise ValueError(f"unknown market {payload.market_code}")

    recent_desc = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id)
            .order_by(PricePoint.timestamp.desc())
            .limit(168)
        ).all()
    )
    prices = list(reversed(recent_desc))
    latest_price = prices[-1] if prices else None
    latest_price_ts = _price_ts(latest_price.timestamp) if latest_price else None

    forecast_stmt = select(Forecast).where(Forecast.market_id == market.id)
    if payload.target_timestamp is not None:
        target_utc = _price_ts(payload.target_timestamp)
        forecasts = list(
            db.scalars(
                forecast_stmt.order_by(Forecast.forecast_for_timestamp.asc()).limit(168)
            ).all()
        )
        forecast = min(
            forecasts,
            key=lambda item: abs((_price_ts(item.forecast_for_timestamp) - target_utc).total_seconds()),
            default=None,
        )
    else:
        if latest_price_ts is not None:
            forecast_stmt = forecast_stmt.where(Forecast.forecast_for_timestamp > latest_price_ts)
        forecast = db.scalar(forecast_stmt.order_by(Forecast.forecast_for_timestamp.asc()).limit(1))
        if forecast is None:
            forecast = db.scalar(
                select(Forecast)
                .where(Forecast.market_id == market.id)
                .order_by(Forecast.forecast_for_timestamp.desc())
                .limit(1)
            )

    spot = float(latest_price.price_value) if latest_price else float(forecast.point_estimate if forecast else 1.0)
    if spot <= 0:
        spot = max(float(forecast.point_estimate if forecast else 1.0), 1.0)
    point = float(forecast.point_estimate) if forecast else spot
    target_timestamp = (
        _price_ts(forecast.forecast_for_timestamp)
        if forecast
        else datetime.now(timezone.utc) + timedelta(hours=payload.horizon_hours)
    )
    currency = (
        getattr(latest_price, "currency", None)
        or getattr(forecast, "currency", None)
        or "USD"
    )
    try:
        from app.services.fx import fx_to_gbp

        fx = float(fx_to_gbp(currency))
    except Exception:  # noqa: BLE001 - fallback must never fail on FX
        fx = 1.0 if currency == "GBP" else 0.85 if currency == "EUR" else 0.79

    log_returns: list[float] = []
    for left, right in zip(prices, prices[1:]):
        left_price = float(left.price_value)
        right_price = float(right.price_value)
        if left_price > 0 and right_price > 0:
            log_returns.append(math.log(right_price / left_price))
    if len(log_returns) >= 2:
        mean_return = sum(log_returns) / len(log_returns)
        variance = sum((value - mean_return) ** 2 for value in log_returns) / (len(log_returns) - 1)
        sigma_hourly = math.sqrt(max(variance, 0.0))
    else:
        sigma_hourly = 0.03
    horizon = max(1, int(payload.horizon_hours))
    sigma_return = max(0.02, min(2.0, sigma_hourly * math.sqrt(horizon)))
    expected_return = (point - spot) / max(spot, 1e-9)
    direction_sign = 1.0 if payload.direction == "long" else -1.0
    likely_gbp = direction_sign * float(payload.position_gbp) * expected_return
    pnl_sigma = max(1.0, float(payload.position_gbp) * sigma_return)
    var95_gbp = max(0.0, -(likely_gbp - 1.65 * pnl_sigma))
    risk_gbp = max(var95_gbp, 0.25 * pnl_sigma)
    upside_gbp = likely_gbp + 1.65 * pnl_sigma
    prob_loss = min(1.0, max(0.0, _normal_cdf(-likely_gbp / pnl_sigma)))
    edge = likely_gbp / risk_gbp if risk_gbp > 0 else 0.0
    action = "clear" if likely_gbp > 0 and prob_loss < 0.45 else "watch" if prob_loss < 0.7 else "block"

    return RiskAssessmentResponse(
        market_code=market.code,
        market_name=market.name,
        as_of=datetime.now(timezone.utc),
        position_gbp=float(payload.position_gbp),
        direction=payload.direction,
        horizon_hours=horizon,
        target_timestamp=target_timestamp,
        spot_price=round(spot, 2),
        forecast_price=round(point, 2),
        expected_price=round(point, 2),
        sigma_price=round(spot * sigma_return, 2),
        sigma_hourly_pct=round(sigma_hourly * 100.0, 3),
        expected_return_pct=round(direction_sign * expected_return * 100.0, 3),
        sigma_return_pct=round(sigma_return * 100.0, 3),
        risk_gbp=round(risk_gbp, 2),
        likely_gbp=round(likely_gbp, 2),
        upside_gbp=round(upside_gbp, 2),
        risk_metric="fast_stored_forecast",
        var95_gbp=round(var95_gbp, 2),
        prob_loss=round(prob_loss, 4),
        max_drawdown_gbp=round(risk_gbp * 0.8, 2),
        fx_to_gbp=round(fx, 6),
        price_currency=currency,
        n_paths=0,
        edge_score=round(float(max(-2.0, min(2.0, edge))), 3),
        confidence=0.35,
        regime="fallback",
        catalyst_severity=0.0,
        asymmetry=0.0,
        tail_multiplier=1.0,
        scorer_provider="stored-forecast-fallback",
        rationale=f"Fast stored-forecast fallback used because full risk calculation was unavailable: {reason[:160]}",
        scenarios=[],
        price_paths=[],
        coefficients={
            "items": [
                {
                    "key": "spot_price",
                    "label": "Spot price",
                    "value": round(spot, 4),
                    "unit": f"{currency}/MWh",
                    "group": "forecast",
                    "description": "Latest stored market price used by fallback risk.",
                },
                {
                    "key": "forecast_price",
                    "label": "Stored forecast",
                    "value": round(point, 4),
                    "unit": f"{currency}/MWh",
                    "group": "forecast",
                    "description": "Nearest stored forecast point used by fallback risk.",
                },
                {
                    "key": "sigma_return",
                    "label": "Fallback sigma",
                    "value": round(sigma_return, 6),
                    "unit": "return",
                    "group": "realised_vol",
                    "description": "Recent realised volatility scaled to the chosen horizon.",
                },
            ],
            "equation_summary": "Fallback P&L uses stored forecast return plus recent realised volatility.",
        },
        decision_gate={
            "action": action,
            "score": round(float(max(0.0, min(100.0, 50.0 + edge * 25.0 - prob_loss * 20.0))), 1),
            "label": "Fallback read",
            "reasons": ["Full Monte Carlo unavailable; using stored forecast fallback."],
            "checks": [
                {"label": "Fallback reason", "status": "warn", "value": reason[:80]},
                {"label": "Loss probability", "status": "warn" if prob_loss < 0.7 else "fail", "value": f"{prob_loss * 100:.1f}%"},
            ],
        },
    )


@public_router.get("/health", response_model=HealthResponse)
@limiter.exempt
def health(background_tasks: BackgroundTasks) -> HealthResponse:
    _schedule_data_refresh(background_tasks)
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc), database="configured")


@router.get("/markets", response_model=list[MarketRead])
def get_markets(db: Session = Depends(get_db)) -> list[MarketRead]:
    markets = list_markets(db)
    return [_market_read(market) for market in markets]


@router.get("/markets/overview", response_model=list[MarketOverviewItem])
def get_markets_overview(db: Session = Depends(get_db)) -> list[MarketOverviewItem]:
    """Single-call home-page payload (plan §4). Additive — does not
    replace /markets, /markets/{id}/prices, or /markets/{id}/forecast.
    """
    entries = build_markets_overview(db)
    return [MarketOverviewItem.model_validate(market_overview_to_dict(entry)) for entry in entries]


@router.get("/markets/{market_id}", response_model=MarketRead)
def get_market(market_id: int, db: Session = Depends(get_db)) -> MarketRead:
    market = get_market_by_id(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return _market_read(market)


@router.get("/markets/{market_id}/prices", response_model=list[PricePointRead])
def get_prices(market_id: int, limit: int = Query(default=720, ge=1, le=8760), db: Session = Depends(get_db)) -> list[PricePointRead]:
    from app.services.forecast_service import list_recent_prices

    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [PricePointRead.model_validate(item) for item in list_recent_prices(db, market_id, limit=limit)]


@router.get("/markets/{market_id}/history", response_model=list[PricePointRead])
def get_market_history(
    market_id: int,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> list[PricePointRead]:
    from app.services.forecast_service import list_price_history

    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    if from_ts and to_ts and from_ts > to_ts:
        raise HTTPException(status_code=400, detail="'from' must be before 'to'")
    prices = list_price_history(db, market_id, start=from_ts, end=to_ts)
    return [PricePointRead.model_validate(item) for item in prices]


@router.get("/markets/{market_id}/timeseries", response_model=list[MarketTimeseriesPoint])
def get_market_timeseries(
    market_id: int,
    series: str = Query(default="demand,wind,solar"),
    limit: int = Query(default=720, ge=1, le=8760),
    db: Session = Depends(get_db),
) -> list[MarketTimeseriesPoint]:
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    requested = {item.strip().lower() for item in series.split(",") if item.strip()}
    allowed = {"demand", "wind", "solar"}
    if not requested <= allowed:
        raise HTTPException(status_code=400, detail="Unsupported timeseries")

    rows: dict[datetime, dict[str, float | datetime | None]] = {}
    if "demand" in requested:
        demand_points = list(
            db.scalars(
                select(DemandPoint)
                .where(DemandPoint.market_id == market_id)
                .order_by(DemandPoint.timestamp.desc())
                .limit(limit)
            ).all()
        )
        for point in demand_points:
            rows.setdefault(point.timestamp, {"timestamp": point.timestamp})["demand_mw"] = point.demand_mw
    if requested & {"wind", "solar"}:
        weather_points = list(
            db.scalars(
                select(WeatherPoint)
                .where(WeatherPoint.market_id == market_id)
                .order_by(WeatherPoint.timestamp.desc())
                .limit(limit)
            ).all()
        )
        for point in weather_points:
            row = rows.setdefault(point.timestamp, {"timestamp": point.timestamp})
            if "wind" in requested:
                row["wind_mw"] = point.wind_generation_estimate
            if "solar" in requested:
                row["solar_mw"] = point.solar_generation_estimate

    out: list[MarketTimeseriesPoint] = []
    for timestamp in sorted(rows):
        row = rows[timestamp]
        demand = float(row["demand_mw"]) if row.get("demand_mw") else None
        wind = float(row["wind_mw"]) if row.get("wind_mw") else None
        solar = float(row["solar_mw"]) if row.get("solar_mw") else None
        out.append(
            MarketTimeseriesPoint(
                timestamp=timestamp,
                demand_mw=demand,
                wind_mw=wind,
                solar_mw=solar,
                wind_share=round(wind / demand, 4) if demand and wind is not None else None,
                solar_share=round(solar / demand, 4) if demand and solar is not None else None,
            )
        )
    return out


@router.get("/markets/{market_id}/forecast", response_model=list[ForecastRead])
def get_market_forecast(market_id: int, limit: int = Query(default=48, le=168), db: Session = Depends(get_db)) -> list[ForecastRead]:
    from app.services.forecast_service import list_forecasts

    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    forecasts = list_forecasts(db, market_id, limit)
    return [_forecast_read(item) for item in forecasts]


@router.post("/forecasts/run", response_model=ForecastRunResponse)
def run_forecast(
    market_code: str = Query(default="ERCOT_NORTH"),
    horizon_hours: int = Query(default=48, ge=12, le=96),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ForecastRunResponse:
    from app.services.alert_service import refresh_alerts_for_market
    from app.services.forecast_service import run_forecast_for_market

    market = get_market_by_code(db, market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=horizon_hours)
    refresh_alerts_for_market(db, market.id)
    write_audit_log(
        db,
        actor=_actor(user),
        action="forecast.run",
        target=f"market:{market.code}",
        after={"horizon_hours": horizon_hours, "forecast_count": len(forecasts), "metrics": metrics},
    )
    return ForecastRunResponse(
        market=_market_read(market),
        forecast_points=[_forecast_read(item) for item in forecasts],
        metrics=metrics,
    )


@router.get("/markets/{market_id}/events", response_model=list[EventRead])
def get_market_events(market_id: int, db: Session = Depends(get_db)) -> list[EventRead]:
    from app.services.event_service import list_events

    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [EventRead.model_validate(item) for item in list_events(db, market_id=market_id)]


@router.get("/events", response_model=list[EventRead])
def get_events(db: Session = Depends(get_db)) -> list[EventRead]:
    from app.services.event_service import list_events

    return [EventRead.model_validate(item) for item in list_events(db)]


@router.get("/events/{event_id}/analogues", response_model=list[EventRead])
def get_event_analogues(event_id: int, db: Session = Depends(get_db)) -> list[EventRead]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return [EventRead.model_validate(item) for item in find_analogues(event, db)]


@router.get("/markets/{market_id}/news", response_model=list[NewsArticleRead])
def get_market_news(market_id: int, db: Session = Depends(get_db)) -> list[NewsArticleRead]:
    from app.services.news_service import list_news_articles

    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return list_news_articles(db, market_id=market_id)


@router.get("/news/sources", response_model=list[NewsSourceRead])
def get_news_sources() -> list[NewsSourceRead]:
    from app.services.news_service import list_news_sources

    return list_news_sources()


@router.get("/integrations/power-bi/embed-config", response_model=PowerBIEmbedConfig)
def get_power_bi_embed_config(
    market_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PowerBIEmbedConfig:
    from app.services.power_bi import PowerBIIntegrationError, build_power_bi_embed_config

    if market_code and not get_market_by_code(db, market_code):
        raise HTTPException(status_code=404, detail="Market not found")
    try:
        return build_power_bi_embed_config(market_code=market_code)
    except PowerBIIntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/articles/ingest", response_model=Optional[EventRead])
def post_article(
    payload: ArticleIngestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> EventRead | None:
    from app.services.event_service import ingest_article

    event = ingest_article(db, payload)
    write_audit_log(
        db,
        actor=_actor(user),
        action="article.ingest",
        target=f"article:{payload.source_url}",
        after=EventRead.model_validate(event).model_dump(mode="json") if event else None,
    )
    return EventRead.model_validate(event) if event else None


@router.get("/markets/{market_id}/alerts", response_model=list[AlertRead])
def get_market_alerts(market_id: int, db: Session = Depends(get_db)) -> list[AlertRead]:
    from app.services.alert_service import list_alerts

    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [AlertRead.model_validate(item) for item in list_alerts(db, market_id)]


@router.post("/markets/{market_code}/refresh")
def refresh_market_data(
    market_code: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Trigger immediate data refresh for a market and invalidate forecast cache."""
    from app.core.config import get_settings
    from app.services.forecast_service import invalidate_forecast_cache
    from app.ingestion.real_data import populate_market_real_data

    market = get_market_by_code(db, market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    settings = get_settings()
    try:
        sources = populate_market_real_data(
            db=db, market=market, market_code=market_code,
            eia_api_key=settings.eia_api_key, days=1,
        )
        invalidate_forecast_cache(market_code)
        db.commit()
        response = {"status": "refreshed", "market": market_code, "sources": sources}
        write_audit_log(
            db,
            actor=_actor(user),
            action="market.refresh",
            target=f"market:{market_code}",
            after=response,
        )
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/risk-assessment", response_model=RiskAssessmentResponse)
@limiter.limit(RISK_ASSESSMENT_LIMIT)
def post_risk_assessment(
    request: Request,
    response: Response,
    payload: RiskAssessmentRequest = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RiskAssessmentResponse:
    from app.services.risk_engine import RiskInputs, ScenarioSpec, assess_risk

    del request
    del response
    try:
        result = assess_risk(
            db,
            RiskInputs(
                market_code=payload.market_code,
                position_gbp=payload.position_gbp,
                position_unit=payload.position_unit,
                position_mwh=payload.position_mwh,
                hedge_ratio=payload.hedge_ratio,
                horizon_hours=payload.horizon_hours,
                target_timestamp=payload.target_timestamp,
                direction=payload.direction,
                n_paths=payload.n_paths,
                scenarios=[
                    ScenarioSpec(
                        name=s.name,
                        sigma_multiplier=s.sigma_multiplier,
                        drift_shift=s.drift_shift,
                        spot_shock_pct=s.spot_shock_pct,
                    )
                    for s in payload.scenarios
                ],
                basis_against_market_code=payload.basis_against_market_code,
                basis_direction=payload.basis_direction,
                path_sample_size=payload.path_sample_size or None,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - risk endpoint should degrade, not fail the page
        logger.warning("risk assessment fallback for %s: %s", payload.market_code, exc)
        result = _fallback_risk_assessment(db, payload, reason=str(exc)).model_dump()
    if not payload.preview:
        row = log_risk_assessment(db, result, user_id=user.id)
        write_audit_log(
            db,
            actor=_actor(user),
            action="risk.assessment",
            target=f"risk_assessment:{row.id if row else result['market_code']}",
            after={key: result.get(key) for key in ("market_code", "position_gbp", "direction", "horizon_hours", "risk_gbp", "likely_gbp", "upside_gbp")},
        )
    return RiskAssessmentResponse(**result)


@router.post("/risk-assessment/solve", response_model=RiskSolveResponse)
def post_risk_assessment_solve(
    payload: RiskSolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RiskSolveResponse:
    from app.services.risk_solver import RiskSolveInputs, solve_position_for_risk

    try:
        result = solve_position_for_risk(
            db,
            RiskSolveInputs(
                market_code=payload.market_code,
                max_risk_gbp=payload.max_risk_gbp,
                horizon_hours=payload.horizon_hours,
                direction=payload.direction,
                position_unit=payload.position_unit,
                target_timestamp=payload.target_timestamp,
            ),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "unknown market" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)
    row = log_risk_assessment(db, result["assessment"], user_id=user.id)
    write_audit_log(
        db,
        actor=_actor(user),
        action="risk.solve",
        target=f"risk_assessment:{row.id if row else result['assessment']['market_code']}",
        after={
            "max_risk_gbp": result["max_risk_gbp"],
            "achieved_risk_gbp": result["achieved_risk_gbp"],
            "resolved_request": result["resolved_request"],
        },
    )
    return RiskSolveResponse(**result)


@router.post("/risk-assessment/sensitivity", response_model=RiskSensitivityResponse)
@limiter.limit(SENSITIVITY_LIMIT)
def post_risk_assessment_sensitivity(
    request: Request,
    response: Response,
    payload: RiskSensitivityRequest = Body(...),
    db: Session = Depends(get_db),
) -> RiskSensitivityResponse:
    from app.services.risk_engine import RiskInputs, ScenarioSpec
    from app.services.risk_sensitivity import run_risk_sensitivity

    del request
    del response
    try:
        result = run_risk_sensitivity(
            db,
            RiskInputs(
                market_code=payload.market_code,
                position_gbp=payload.position_gbp,
                position_unit=payload.position_unit,
                position_mwh=payload.position_mwh,
                hedge_ratio=payload.hedge_ratio,
                horizon_hours=payload.horizon_hours,
                target_timestamp=payload.target_timestamp,
                direction=payload.direction,
                n_paths=payload.n_paths,
                scenarios=[
                    ScenarioSpec(
                        name=s.name,
                        sigma_multiplier=s.sigma_multiplier,
                        drift_shift=s.drift_shift,
                        spot_shock_pct=s.spot_shock_pct,
                    )
                    for s in payload.scenarios
                ],
            ),
            [str(item) for item in payload.coefficients_to_perturb],
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "unknown market" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)
    return RiskSensitivityResponse(**result)


@router.post("/risk-assessment/paths", response_model=RiskPathFanResponse)
def post_risk_assessment_paths(
    payload: RiskAssessmentRequest,
    db: Session = Depends(get_db),
) -> RiskPathFanResponse:
    from app.services.risk_engine import RiskInputs, ScenarioSpec, assess_risk

    try:
        result = assess_risk(
            db,
            RiskInputs(
                market_code=payload.market_code,
                position_gbp=payload.position_gbp,
                position_unit=payload.position_unit,
                position_mwh=payload.position_mwh,
                hedge_ratio=payload.hedge_ratio,
                horizon_hours=payload.horizon_hours,
                target_timestamp=payload.target_timestamp,
                direction=payload.direction,
                n_paths=payload.n_paths,
                scenarios=[
                    ScenarioSpec(
                        name=s.name,
                        sigma_multiplier=s.sigma_multiplier,
                        drift_shift=s.drift_shift,
                        spot_shock_pct=s.spot_shock_pct,
                    )
                    for s in payload.scenarios
                ],
                random_seed=260512,
                path_sample_size=200,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return RiskPathFanResponse(
        market_code=result["market_code"],
        horizon_hours=result["horizon_hours"],
        path_hours=list(range(int(result["horizon_hours"]) + 1)),
        price_paths=result["price_paths"][:200],
        assessment=RiskAssessmentResponse(**result),
    )


@router.post("/risk-assessment/optimal-hedge", response_model=OptimalHedgeResponse)
def post_optimal_hedge(payload: RiskAssessmentRequest, db: Session = Depends(get_db)) -> OptimalHedgeResponse:
    from app.services.deep_hedger import hedge_features_from_assessment, recommend_hedge_ratio
    from app.services.risk_engine import RiskInputs, assess_risk

    try:
        current = assess_risk(
            db,
            RiskInputs(
                market_code=payload.market_code,
                position_gbp=payload.position_gbp,
                position_unit=payload.position_unit,
                position_mwh=payload.position_mwh,
                hedge_ratio=payload.hedge_ratio,
                horizon_hours=payload.horizon_hours,
                target_timestamp=payload.target_timestamp,
                direction=payload.direction,
                n_paths=payload.n_paths,
            ),
        )
        hedge_ratio = recommend_hedge_ratio(hedge_features_from_assessment(current))
        unhedged_ratio = max(0.0, min(1.0, 1.0 - hedge_ratio))
        hedged = assess_risk(
            db,
            RiskInputs(
                market_code=payload.market_code,
                position_gbp=payload.position_gbp,
                position_unit=payload.position_unit,
                position_mwh=payload.position_mwh,
                hedge_ratio=unhedged_ratio,
                horizon_hours=payload.horizon_hours,
                target_timestamp=payload.target_timestamp,
                direction=payload.direction,
                n_paths=payload.n_paths,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return OptimalHedgeResponse(
        market_code=payload.market_code,
        hedge_ratio=round(float(hedge_ratio), 4),
        unhedged_ratio=round(float(unhedged_ratio), 4),
        risk_before_gbp=float(current["risk_gbp"]),
        risk_after_gbp=float(hedged["risk_gbp"]),
        likely_cost_gbp=round(float(current["likely_gbp"]) - float(hedged["likely_gbp"]), 2),
        current_assessment=RiskAssessmentResponse(**current),
        hedged_assessment=RiskAssessmentResponse(**hedged),
    )


@router.post("/risk-assessment/export")
def post_risk_assessment_export(
    payload: RiskAssessmentRequest,
    format: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    from app.services.export_pack import build_risk_export

    try:
        content, media_type, filename, audit_payload = build_risk_export(db, payload, format)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "unknown market" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)
    write_audit_log(
        db,
        actor=_actor(user),
        action="risk.export",
        target=f"market:{payload.market_code}",
        after=audit_payload,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/portfolio-risk", response_model=PortfolioRiskResponse)
def post_portfolio_risk(payload: PortfolioRiskRequest, db: Session = Depends(get_db)) -> PortfolioRiskResponse:
    from app.services.portfolio_risk import PortfolioPositionInput, run_portfolio_risk

    try:
        result = run_portfolio_risk(
            db,
            [
                PortfolioPositionInput(
                    market_code=position.market_code,
                    position_gbp=position.position_gbp,
                    direction=position.direction,
                )
                for position in payload.positions
            ],
            horizon_hours=payload.horizon_hours,
            n_paths=payload.n_paths,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PortfolioRiskResponse(**result)


@router.get("/markets/{market_id}/risk-calibration", response_model=RiskCalibrationResponse)
def get_market_risk_calibration(market_id: int, db: Session = Depends(get_db)) -> RiskCalibrationResponse:
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return RiskCalibrationResponse(**risk_calibration_for_market(db, market_id))


@router.post("/decisions", response_model=DecisionRead)
def post_decision(
    payload: DecisionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> DecisionRead:
    try:
        result = create_decision(db, payload, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    write_audit_log(
        db,
        actor=_actor(user),
        action="decision.create",
        target=f"decision:{result['id']}",
        after=result,
    )
    return DecisionRead(**result)


@router.get("/decisions", response_model=list[DecisionRead])
def get_decisions(
    market_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[DecisionRead]:
    if market_id is not None and not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [DecisionRead(**item) for item in list_decisions(db, market_id=market_id, user_id=user.id)]


@router.patch("/decisions/{decision_id}", response_model=DecisionRead)
def patch_decision(
    decision_id: int,
    payload: DecisionUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> DecisionRead:
    before = next((item for item in list_decisions(db, user_id=user.id) if item["id"] == decision_id), None)
    try:
        result = update_decision(db, decision_id, payload, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    write_audit_log(
        db,
        actor=_actor(user),
        action="decision.update",
        target=f"decision:{decision_id}",
        before=before,
        after=result,
    )
    return DecisionRead(**result)


@router.delete("/decisions/{decision_id}", response_model=dict[str, int])
def remove_decision(
    decision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, int]:
    before = next((item for item in list_decisions(db, user_id=user.id) if item["id"] == decision_id), None)
    try:
        delete_decision(db, decision_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    write_audit_log(
        db,
        actor=_actor(user),
        action="decision.delete",
        target=f"decision:{decision_id}",
        before=before,
        after=None,
    )
    return {"deleted_id": decision_id}


@router.get("/audit", response_model=list[AuditLogRead])
def get_audit_logs(
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _: User = Depends(audit_user),
) -> list[AuditLogRead]:
    if from_ts and to_ts and from_ts > to_ts:
        raise HTTPException(status_code=400, detail="'from' must be before 'to'")
    return [_audit_read(row) for row in list_audit_logs(db, from_ts=from_ts, to_ts=to_ts)]


@router.get("/markets/{market_id}/backtest/latest", response_model=dict[str, Any] | None)
def get_latest_market_backtest(market_id: int, db: Session = Depends(get_db)) -> dict[str, Any] | None:
    from app.services.backtest_reports import latest_backtest_report_for_market

    market = get_market_by_id(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return latest_backtest_report_for_market(market.code)


@router.get("/grid/topology", response_model=dict[str, Any])
def get_grid_topology() -> dict[str, Any]:
    """E.5 — return the canonical grid topology bundle for the UI graph."""
    from app.grid.topology import load_topology_bundle
    return load_topology_bundle()


@router.get("/grid/flows", response_model=dict[str, Any])
def get_grid_flows() -> dict[str, Any]:
    """E.5 — solve DC-OPF on the seed topology with seed dispatch and return
    flows + LMPs + binding lines for the topology UI."""
    from app.grid.dc_opf import solve_dc_opf
    from app.grid.topology import bundle_to_topology, load_topology_bundle

    bundle = load_topology_bundle()
    topology = bundle_to_topology(bundle)
    # Give every bus a representative load equal to 10% of its gen_max,
    # so the OPF has something to dispatch under the seed.
    for bus in topology.buses:
        if bus.load_mw == 0.0 and bus.gen_max_mw > 0:
            bus.load_mw = round(bus.gen_max_mw * 0.10, 1)
    result = solve_dc_opf(topology)
    if not result.success:
        raise HTTPException(status_code=500, detail=f"OPF infeasible: {result.message}")

    edges = []
    for line in topology.lines:
        flow = result.flows_mw.get((line.from_bus, line.to_bus), 0.0)
        util = abs(flow) / line.limit_mw if line.limit_mw > 0 else 0.0
        edges.append({
            "from_bus": line.from_bus,
            "to_bus": line.to_bus,
            "flow_mw": round(float(flow), 2),
            "limit_mw": round(float(line.limit_mw), 2),
            "utilisation": round(float(util), 4),
            "binding": (line.from_bus, line.to_bus) in result.binding_lines,
        })
    return {
        "buses": [
            {
                "name": b.name,
                "load_mw": round(float(b.load_mw), 2),
                "gen_mw": round(float(result.gen_mw.get(b.name, 0.0)), 2),
                "gen_max_mw": round(float(b.gen_max_mw), 2),
                "lmp": round(float(result.lmps.get(b.name, 0.0)), 4),
                "is_reference": b.is_reference,
                "market_code": next(
                    (entry.get("market_code") for entry in bundle["buses"]
                     if entry["name"] == b.name),
                    None,
                ),
            }
            for b in topology.buses
        ],
        "edges": edges,
        "objective_cost": round(float(result.objective_cost), 2),
    }


@router.get("/dashboard/{market_code}", response_model=DashboardResponse)
def get_dashboard(
    market_code: str,
    history_hours: int = Query(default=720, ge=1, le=8760),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    from app.services.alert_service import list_alerts, refresh_alerts_for_market
    from app.services.backtest_reports import dashboard_backtest_metrics
    from app.services.event_service import list_events
    from app.services.forecast_service import list_forecasts, list_recent_prices, run_forecast_for_market
    from app.services.news_service import list_news_articles, list_news_sources

    market = get_market_by_code(db, market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    try:
        forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=48)
    except Exception as exc:  # noqa: BLE001 - dashboard should degrade, not fail the page
        logger.warning("dashboard forecast fallback for %s: %s", market.code, exc)
        forecasts = list_forecasts(db, market.id, 48)
        metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.5, "spike_precision": 0.0}
    refresh_alerts_for_market(db, market.id)
    latest_forecast = forecasts[0] if forecasts else None
    prices = list_recent_prices(db, market.id, history_hours)
    events = list_events(db, market.id, 72)
    news = list_news_articles(db, market.id, 720, 20)
    alerts = list_alerts(db, market.id, 72)

    avg_price = round(_mean_finite([point.price_value for point in prices[-24:]]), 2)
    avg_spike_probability = round(_mean_finite([f.spike_probability for f in forecasts[:12]]), 3)
    high_severity_events = float(sum(1 for event in events if event.severity == "high"))

    payload = DashboardResponse(
        market=_market_read(market),
        latest_forecast=_forecast_read(latest_forecast) if latest_forecast else None,
        forecasts=[_forecast_read(item) for item in forecasts],
        recent_prices=[PricePointRead.model_validate(item) for item in prices],
        recent_events=[EventRead.model_validate(item) for item in events],
        recent_news=news,
        tracked_sources=list_news_sources(),
        active_alerts=[AlertRead.model_validate(item) for item in alerts],
        key_metrics={
            "avg_price_24h": avg_price,
            "avg_spike_probability_12h": avg_spike_probability,
            "high_severity_events": high_severity_events,
            "model_mae": _finite_float(metrics.get("mae")),
            "model_rmse": _finite_float(metrics.get("rmse")),
            "directional_accuracy": _finite_float(metrics.get("directional_accuracy"), 0.5),
            "spike_precision": _finite_float(metrics.get("spike_precision")),
            **dashboard_backtest_metrics(market.code),
            **_price_provenance_metrics(prices),
        },
    )
    return _safe_json_response(payload.model_dump())


@router.get(
    "/dashboard/{market_code}/summary",
    response_model=DashboardSummaryResponse,
)
def get_dashboard_summary(
    market_code: str,
    history_hours: int = Query(default=168, ge=1, le=8760),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    from app.services.forecast_service import list_forecasts, list_recent_prices, run_forecast_for_market

    """Lightweight first-screen payload for the market workbench.

    Plan §5.2 — additive endpoint. Returns only what the hero, trade
    input, and chart need; does NOT refresh alerts, fetch news, fetch
    events, or load tracked sources. The full `/dashboard/{market_code}`
    endpoint remains the canonical compatibility surface.
    """
    market = get_market_by_code(db, market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    try:
        forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=48)
    except Exception as exc:  # noqa: BLE001 - first-screen payload should degrade, not fail
        logger.warning("dashboard summary forecast fallback for %s: %s", market.code, exc)
        forecasts = list_forecasts(db, market.id, 48)
        metrics = {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.5, "spike_precision": 0.0}
    latest_forecast = forecasts[0] if forecasts else None
    prices = list_recent_prices(db, market.id, history_hours)

    avg_price = round(_mean_finite([point.price_value for point in prices[-24:]]), 2)
    avg_spike_probability = round(_mean_finite([f.spike_probability for f in forecasts[:12]]), 3)

    payload = DashboardSummaryResponse(
        market=_market_read(market),
        latest_forecast=_forecast_read(latest_forecast) if latest_forecast else None,
        forecasts=[_forecast_read(item) for item in forecasts],
        recent_prices=[PricePointRead.model_validate(item) for item in prices],
        key_metrics={
            "avg_price_24h": avg_price,
            "avg_spike_probability_12h": avg_spike_probability,
            "model_mae": _finite_float(metrics.get("mae")),
            "model_rmse": _finite_float(metrics.get("rmse")),
            "directional_accuracy": _finite_float(metrics.get("directional_accuracy"), 0.5),
            "spike_precision": _finite_float(metrics.get("spike_precision")),
            **_price_provenance_metrics(prices),
        },
        data_status=_market_data_status(market),
    )
    return _safe_json_response(payload.model_dump())
