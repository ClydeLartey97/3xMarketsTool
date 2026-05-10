from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import DemandPoint, Forecast, WeatherPoint
from app.schemas.domain import (
    AlertRead,
    ArticleIngestRequest,
    DashboardResponse,
    DecisionCreateRequest,
    DecisionRead,
    EventRead,
    ForecastRunResponse,
    ForecastRead,
    HealthResponse,
    MarketRead,
    MarketTimeseriesPoint,
    NewsArticleRead,
    NewsSourceRead,
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
from app.services.risk_engine import RiskInputs, ScenarioSpec, assess_risk
from app.services.decision_diary import create_decision, list_decisions
from app.services.risk_calibration import log_risk_assessment, risk_calibration_for_market
from app.services.risk_sensitivity import run_risk_sensitivity
from app.services.risk_solver import RiskSolveInputs, solve_position_for_risk
from app.services.alert_service import list_alerts, refresh_alerts_for_market
from app.services.backtest_reports import dashboard_backtest_metrics, latest_backtest_report_for_market
from app.services.event_service import ingest_article, list_events
from app.services.forecast_service import (
    invalidate_forecast_cache,
    list_forecasts,
    list_price_history,
    list_recent_prices,
    run_forecast_for_market,
)
from app.services.market_service import get_market_by_code, get_market_by_id, list_markets
from app.services.news_service import list_news_articles, list_news_sources

router = APIRouter()


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


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc), database="configured")


@router.get("/markets", response_model=list[MarketRead])
def get_markets(db: Session = Depends(get_db)) -> list[MarketRead]:
    markets = list_markets(db)
    return [_market_read(market) for market in markets]


@router.get("/markets/{market_id}", response_model=MarketRead)
def get_market(market_id: int, db: Session = Depends(get_db)) -> MarketRead:
    market = get_market_by_id(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return _market_read(market)


@router.get("/markets/{market_id}/prices", response_model=list[PricePointRead])
def get_prices(market_id: int, limit: int = Query(default=720, ge=1, le=8760), db: Session = Depends(get_db)) -> list[PricePointRead]:
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
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    forecasts = list_forecasts(db, market_id, limit)
    return [ForecastRead.model_validate(item) for item in forecasts]


@router.post("/forecasts/run", response_model=ForecastRunResponse)
def run_forecast(
    market_code: str = Query(default="ERCOT_NORTH"),
    horizon_hours: int = Query(default=48, ge=12, le=96),
    db: Session = Depends(get_db),
) -> ForecastRunResponse:
    market = get_market_by_code(db, market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=horizon_hours)
    refresh_alerts_for_market(db, market.id)
    return ForecastRunResponse(
        market=_market_read(market),
        forecast_points=[ForecastRead.model_validate(item) for item in forecasts],
        metrics=metrics,
    )


@router.get("/markets/{market_id}/events", response_model=list[EventRead])
def get_market_events(market_id: int, db: Session = Depends(get_db)) -> list[EventRead]:
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [EventRead.model_validate(item) for item in list_events(db, market_id=market_id)]


@router.get("/events", response_model=list[EventRead])
def get_events(db: Session = Depends(get_db)) -> list[EventRead]:
    return [EventRead.model_validate(item) for item in list_events(db)]


@router.get("/markets/{market_id}/news", response_model=list[NewsArticleRead])
def get_market_news(market_id: int, db: Session = Depends(get_db)) -> list[NewsArticleRead]:
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return list_news_articles(db, market_id=market_id)


@router.get("/news/sources", response_model=list[NewsSourceRead])
def get_news_sources() -> list[NewsSourceRead]:
    return list_news_sources()


@router.post("/articles/ingest", response_model=Optional[EventRead])
def post_article(payload: ArticleIngestRequest, db: Session = Depends(get_db)) -> EventRead | None:
    event = ingest_article(db, payload)
    return EventRead.model_validate(event) if event else None


@router.get("/markets/{market_id}/alerts", response_model=list[AlertRead])
def get_market_alerts(market_id: int, db: Session = Depends(get_db)) -> list[AlertRead]:
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [AlertRead.model_validate(item) for item in list_alerts(db, market_id)]


@router.post("/markets/{market_code}/refresh")
def refresh_market_data(market_code: str, db: Session = Depends(get_db)) -> dict:
    """Trigger immediate data refresh for a market and invalidate forecast cache."""
    from app.core.config import get_settings
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
        return {"status": "refreshed", "market": market_code, "sources": sources}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/risk-assessment", response_model=RiskAssessmentResponse)
def post_risk_assessment(payload: RiskAssessmentRequest, db: Session = Depends(get_db)) -> RiskAssessmentResponse:
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
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    log_risk_assessment(db, result)
    return RiskAssessmentResponse(**result)


@router.post("/risk-assessment/solve", response_model=RiskSolveResponse)
def post_risk_assessment_solve(payload: RiskSolveRequest, db: Session = Depends(get_db)) -> RiskSolveResponse:
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
    log_risk_assessment(db, result["assessment"])
    return RiskSolveResponse(**result)


@router.post("/risk-assessment/sensitivity", response_model=RiskSensitivityResponse)
def post_risk_assessment_sensitivity(
    payload: RiskSensitivityRequest,
    db: Session = Depends(get_db),
) -> RiskSensitivityResponse:
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


@router.get("/markets/{market_id}/risk-calibration", response_model=RiskCalibrationResponse)
def get_market_risk_calibration(market_id: int, db: Session = Depends(get_db)) -> RiskCalibrationResponse:
    if not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return RiskCalibrationResponse(**risk_calibration_for_market(db, market_id))


@router.post("/decisions", response_model=DecisionRead)
def post_decision(payload: DecisionCreateRequest, db: Session = Depends(get_db)) -> DecisionRead:
    try:
        result = create_decision(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DecisionRead(**result)


@router.get("/decisions", response_model=list[DecisionRead])
def get_decisions(
    market_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DecisionRead]:
    if market_id is not None and not get_market_by_id(db, market_id):
        raise HTTPException(status_code=404, detail="Market not found")
    return [DecisionRead(**item) for item in list_decisions(db, market_id=market_id)]


@router.get("/markets/{market_id}/backtest/latest", response_model=dict[str, Any] | None)
def get_latest_market_backtest(market_id: int, db: Session = Depends(get_db)) -> dict[str, Any] | None:
    market = get_market_by_id(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return latest_backtest_report_for_market(market.code)


@router.get("/dashboard/{market_code}", response_model=DashboardResponse)
def get_dashboard(
    market_code: str,
    history_hours: int = Query(default=720, ge=1, le=8760),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    market = get_market_by_code(db, market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=48)
    refresh_alerts_for_market(db, market.id)
    latest_forecast = forecasts[0] if forecasts else None
    prices = list_recent_prices(db, market.id, history_hours)
    events = list_events(db, market.id, 72)
    news = list_news_articles(db, market.id, 168, 20)
    alerts = list_alerts(db, market.id, 72)

    avg_price = round(sum(point.price_value for point in prices[-24:]) / max(len(prices[-24:]), 1), 2)
    avg_spike_probability = round(sum(f.spike_probability for f in forecasts[:12]) / max(len(forecasts[:12]), 1), 3)
    high_severity_events = float(sum(1 for event in events if event.severity == "high"))

    return DashboardResponse(
        market=_market_read(market),
        latest_forecast=ForecastRead.model_validate(latest_forecast) if latest_forecast else None,
        forecasts=[ForecastRead.model_validate(item) for item in forecasts],
        recent_prices=[PricePointRead.model_validate(item) for item in prices],
        recent_events=[EventRead.model_validate(item) for item in events],
        recent_news=news,
        tracked_sources=list_news_sources(),
        active_alerts=[AlertRead.model_validate(item) for item in alerts],
        key_metrics={
            "avg_price_24h": avg_price,
            "avg_spike_probability_12h": avg_spike_probability,
            "high_severity_events": high_severity_events,
            "model_mae": metrics["mae"],
            "model_rmse": metrics["rmse"],
            "directional_accuracy": metrics["directional_accuracy"],
            "spike_precision": metrics["spike_precision"],
            **dashboard_backtest_metrics(market.code),
            **_price_provenance_metrics(prices),
        },
    )
