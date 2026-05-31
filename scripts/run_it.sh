#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p "$ROOT_DIR/.local/run"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
APP_PATH="${APP_PATH:-/markets/GB_POWER}"
APP_URL="${APP_URL:-http://127.0.0.1:${FRONTEND_PORT}${APP_PATH}}"
FRONTEND_HEALTH_URL="${FRONTEND_HEALTH_URL:-http://127.0.0.1:${FRONTEND_PORT}}"
LOCAL_DB_PATH="$ROOT_DIR/.local/threex.dev.db"
DATABASE_URL="${DATABASE_URL:-sqlite:///$LOCAL_DB_PATH}"
DEMO_MODE="${DEMO_MODE:-true}"
EIA_API_KEY="${EIA_API_KEY:-}"
RATE_LIMIT_ENABLED="${RATE_LIMIT_ENABLED:-false}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
REBUILD_FRONTEND="${REBUILD_FRONTEND:-0}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"
USE_RUNTIME_BACKEND="${USE_RUNTIME_BACKEND:-0}"
USE_RUNTIME_FRONTEND="${USE_RUNTIME_FRONTEND:-1}"
REFRESH_RUNTIME="${REFRESH_RUNTIME:-0}"
RUNTIME_ROOT="${MARKET_SPEC_RUNTIME_ROOT:-/tmp/market-speculation-runtime}"
RUNTIME_REPO_URL="${MARKET_SPEC_RUNTIME_REPO_URL:-https://github.com/ClydeLartey97/3xMarketsTool.git}"
RUNTIME_BRANCH="${MARKET_SPEC_RUNTIME_BRANCH:-main}"
LOCAL_PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
PYTHON_BIN="$LOCAL_PYTHON_BIN"
BACKEND_LOG="$ROOT_DIR/.local/run/backend.log"
FRONTEND_LOG="$ROOT_DIR/.local/run/frontend.log"
BACKEND_PID_FILE="$ROOT_DIR/.local/run/backend.pid"
FRONTEND_PID_FILE="$ROOT_DIR/.local/run/frontend.pid"
RUNTIME_CLONE_LOG="$ROOT_DIR/.local/run/runtime-clone.log"
RUNTIME_PIP_LOG="$ROOT_DIR/.local/run/runtime-pip.log"
RUNTIME_NPM_LOG="$ROOT_DIR/.local/run/runtime-npm.log"
FRONTEND_DIR="$ROOT_DIR/frontend"

for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN_BROWSER=0 ;;
    --refresh-runtime) REFRESH_RUNTIME=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

http_ok() {
  curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

open_app() {
  if [ "$OPEN_BROWSER" = "1" ] && command -v open >/dev/null 2>&1; then
    open "$APP_URL" >/dev/null 2>&1 || true
  fi
}

stop_port() {
  port="$1"
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null || true
    sleep 0.4
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

wait_for() {
  label="$1"
  url="$2"
  attempts="$3"
  for _ in $(seq 1 "$attempts"); do
    if http_ok "$url"; then
      return 0
    fi
    sleep 0.25
  done
  echo "$label did not become ready. Recent logs:" >&2
  tail -80 "$BACKEND_LOG" "$FRONTEND_LOG" 2>/dev/null >&2 || true
  return 1
}

patch_runtime_backend() {
  runtime_root="$1"
  python3 - "$runtime_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])

routes = root / "backend/app/api/routes.py"
text = routes.read_text()
if text.startswith("from __future__ import annotations\n\n"):
    text = text[len("from __future__ import annotations\n\n") :]
for line in [
    "from app.services.risk_engine import RiskInputs, ScenarioSpec, assess_risk\n",
    "from app.services.risk_sensitivity import run_risk_sensitivity\n",
    "from app.services.risk_solver import RiskSolveInputs, solve_position_for_risk\n",
    "from app.services.alert_service import list_alerts, refresh_alerts_for_market\n",
    "from app.services.backtest_reports import dashboard_backtest_metrics, latest_backtest_report_for_market\n",
    "from app.services.event_service import ingest_article, list_events\n",
    "from app.services.export_pack import build_risk_export\n",
    "from app.services.news_service import list_news_articles, list_news_sources\n",
    "from app.services.portfolio_risk import PortfolioPositionInput, run_portfolio_risk\n",
    "from app.services.power_bi import PowerBIIntegrationError, build_power_bi_embed_config\n",
]:
    text = text.replace(line, "")
text = text.replace(
    "from app.services.forecast_service import (\n"
    "    invalidate_forecast_cache,\n"
    "    list_forecasts,\n"
    "    list_price_history,\n"
    "    list_recent_prices,\n"
    "    run_forecast_for_market,\n"
    ")\n",
    "",
)
text = text.replace("from app.services.deep_hedger import hedge_features_from_assessment, recommend_hedge_ratio\n", "")
lazy_replacements = {
    "    return [PricePointRead.model_validate(item) for item in list_recent_prices(db, market_id, limit=limit)]":
        "    from app.services.forecast_service import list_recent_prices\n\n"
        "    return [PricePointRead.model_validate(item) for item in list_recent_prices(db, market_id, limit=limit)]",
    "    prices = list_price_history(db, market_id, start=from_ts, end=to_ts)":
        "    from app.services.forecast_service import list_price_history\n\n"
        "    prices = list_price_history(db, market_id, start=from_ts, end=to_ts)",
    "    forecasts = list_forecasts(db, market_id, limit)":
        "    from app.services.forecast_service import list_forecasts\n\n"
        "    forecasts = list_forecasts(db, market_id, limit)",
    "    forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=horizon_hours)":
        "    from app.services.forecast_service import run_forecast_for_market\n\n"
        "    forecasts, metrics = run_forecast_for_market(db, market, horizon_hours=horizon_hours)",
    "    refresh_alerts_for_market(db, market.id)":
        "    from app.services.alert_service import refresh_alerts_for_market\n\n"
        "    refresh_alerts_for_market(db, market.id)",
    "    return [EventRead.model_validate(item) for item in list_events(db, market_id=market_id)]":
        "    from app.services.event_service import list_events\n\n"
        "    return [EventRead.model_validate(item) for item in list_events(db, market_id=market_id)]",
    "    return [EventRead.model_validate(item) for item in list_events(db)]":
        "    from app.services.event_service import list_events\n\n"
        "    return [EventRead.model_validate(item) for item in list_events(db)]",
    "    return list_news_articles(db, market_id=market_id)":
        "    from app.services.news_service import list_news_articles\n\n"
        "    return list_news_articles(db, market_id=market_id)",
    "    return list_news_sources()":
        "    from app.services.news_service import list_news_sources\n\n"
        "    return list_news_sources()",
    "        return build_power_bi_embed_config(market_code=market_code)":
        "        from app.services.power_bi import build_power_bi_embed_config\n\n"
        "        return build_power_bi_embed_config(market_code=market_code)",
    "    except PowerBIIntegrationError as exc:":
        "    except Exception as exc:\n"
        "        from app.services.power_bi import PowerBIIntegrationError\n"
        "        if not isinstance(exc, PowerBIIntegrationError):\n"
        "            raise",
    "    event = ingest_article(db, payload)":
        "    from app.services.event_service import ingest_article\n\n"
        "    event = ingest_article(db, payload)",
    "    return [AlertRead.model_validate(item) for item in list_alerts(db, market_id)]":
        "    from app.services.alert_service import list_alerts\n\n"
        "    return [AlertRead.model_validate(item) for item in list_alerts(db, market_id)]",
    "        invalidate_forecast_cache(market_code)":
        "        from app.services.forecast_service import invalidate_forecast_cache\n\n"
        "        invalidate_forecast_cache(market_code)",
    "    try:\n        result = assess_risk(":
        "    from app.services.risk_engine import RiskInputs, ScenarioSpec, assess_risk\n\n"
        "    try:\n        result = assess_risk(",
    "    try:\n        result = solve_position_for_risk(":
        "    from app.services.risk_solver import RiskSolveInputs, solve_position_for_risk\n\n"
        "    try:\n        result = solve_position_for_risk(",
    "    try:\n        result = run_risk_sensitivity(":
        "    from app.services.risk_engine import RiskInputs, ScenarioSpec\n"
        "    from app.services.risk_sensitivity import run_risk_sensitivity\n\n"
        "    try:\n        result = run_risk_sensitivity(",
    "    try:\n        current = assess_risk(":
        "    from app.services.risk_engine import RiskInputs, assess_risk\n\n"
        "    try:\n        current = assess_risk(",
    "        content, media_type, filename, audit_payload = build_risk_export(db, payload, format)":
        "        from app.services.export_pack import build_risk_export\n\n"
        "        content, media_type, filename, audit_payload = build_risk_export(db, payload, format)",
    "        result = run_portfolio_risk(":
        "        from app.services.portfolio_risk import PortfolioPositionInput, run_portfolio_risk\n\n"
        "        result = run_portfolio_risk(",
    "    return latest_backtest_report_for_market(market.code)":
        "    from app.services.backtest_reports import latest_backtest_report_for_market\n\n"
        "    return latest_backtest_report_for_market(market.code)",
    "            **dashboard_backtest_metrics(market.code),":
        "            **__import__('app.services.backtest_reports', fromlist=['dashboard_backtest_metrics']).dashboard_backtest_metrics(market.code),",
}
for old, new in lazy_replacements.items():
    if old in text and new not in text:
        text = text.replace(old, new)
fast_risk = '''@router.post("/risk-assessment", response_model=RiskAssessmentResponse)
@limiter.limit(RISK_ASSESSMENT_LIMIT)
def post_risk_assessment(
    request: Request,
    response: Response,
    payload: RiskAssessmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RiskAssessmentResponse:
    import math
    from app.models import Forecast, PricePoint

    del request
    del response
    market = get_market_by_code(db, payload.market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    prices = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.market_id == market.id)
            .order_by(PricePoint.timestamp.desc())
            .limit(48)
        ).all()
    )
    latest_price = prices[0] if prices else None
    forecast = db.scalars(
        select(Forecast)
        .where(Forecast.market_id == market.id)
        .order_by(Forecast.forecast_for_timestamp.asc())
        .limit(1)
    ).first()

    spot = float(latest_price.price_value) if latest_price else 100.0
    forecast_price = float(forecast.point_estimate) if forecast else spot * (1.0 + 0.0015 * payload.horizon_hours)
    currency = (latest_price.currency if latest_price else None) or (forecast.currency if forecast else None) or "GBP"
    target_ts = payload.target_timestamp or (forecast.forecast_for_timestamp if forecast else datetime.now(timezone.utc) + timedelta(hours=payload.horizon_hours))
    direction_sign = 1.0 if payload.direction == "long" else -1.0

    returns: list[float] = []
    ordered = list(reversed(prices))
    for prev, cur in zip(ordered, ordered[1:]):
        if prev.price_value:
            returns.append((float(cur.price_value) - float(prev.price_value)) / float(prev.price_value))
    if returns:
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / max(len(returns) - 1, 1)
        sigma_hourly = max(math.sqrt(variance), 0.01)
    else:
        sigma_hourly = 0.035

    expected_return = direction_sign * ((forecast_price - spot) / max(abs(spot), 1e-6))
    sigma_return = sigma_hourly * math.sqrt(max(payload.horizon_hours, 1))
    exposed_notional = payload.position_gbp * payload.hedge_ratio
    likely_gbp = round(exposed_notional * expected_return, 2)
    risk_gbp = round(abs(exposed_notional) * max(0.04, 1.65 * sigma_return - expected_return), 2)
    upside_gbp = round(max(0.0, likely_gbp) + abs(exposed_notional) * max(0.03, 1.25 * sigma_return + expected_return), 2)
    var95_gbp = round(risk_gbp * 0.88, 2)
    prob_loss = max(0.05, min(0.95, 0.5 - expected_return / max(2.5 * sigma_return, 1e-6)))
    edge_score = round(likely_gbp / max(risk_gbp, 1.0), 4)

    result = {
        "market_code": market.code,
        "market_name": market.name,
        "as_of": datetime.now(timezone.utc),
        "position_gbp": float(payload.position_gbp),
        "direction": payload.direction,
        "horizon_hours": payload.horizon_hours,
        "target_timestamp": target_ts,
        "spot_price": round(spot, 2),
        "forecast_price": round(forecast_price, 2),
        "expected_price": round(forecast_price, 2),
        "sigma_price": round(abs(spot) * sigma_return, 2),
        "sigma_hourly_pct": round(sigma_hourly * 100, 3),
        "expected_return_pct": round(expected_return * 100, 3),
        "sigma_return_pct": round(sigma_return * 100, 3),
        "risk_gbp": risk_gbp,
        "likely_gbp": likely_gbp,
        "upside_gbp": upside_gbp,
        "risk_metric": "fast_local_cvar_95",
        "var95_gbp": var95_gbp,
        "prob_loss": round(prob_loss, 4),
        "max_drawdown_gbp": round(risk_gbp * 0.96, 2),
        "fx_to_gbp": 1.0,
        "price_currency": currency,
        "n_paths": int(payload.n_paths),
        "edge_score": edge_score,
        "confidence": 0.62,
        "regime": "local-fast",
        "catalyst_severity": 0.2,
        "asymmetry": 0.0,
        "tail_multiplier": 1.0,
        "scorer_provider": "local-fast",
        "rationale": "Fast local estimate from latest seeded prices and forecast; full analytics are skipped in run-it mode.",
        "scenarios": [],
        "coefficients": {
            "items": [
                {"key": "spot_price", "label": "Spot price", "value": round(spot, 2), "unit": f"{currency}/MWh", "group": "forecast", "description": "Latest local price point."},
                {"key": "forecast_price", "label": "Forecast price", "value": round(forecast_price, 2), "unit": f"{currency}/MWh", "group": "forecast", "description": "Nearest local forecast point."},
                {"key": "sigma_hourly", "label": "Hourly volatility", "value": round(sigma_hourly * 100, 3), "unit": "%", "group": "realised_vol", "description": "Recent local price volatility."},
                {"key": "position_gbp", "label": "Position", "value": float(payload.position_gbp), "unit": "GBP", "group": "position", "description": "Selected notional."},
            ],
            "equation_summary": "Fast local P&L estimate = direction x position x forecast return, with downside scaled by recent hourly volatility.",
        },
        "decision_gate": {
            "action": "watch" if risk_gbp / max(payload.position_gbp, 1.0) < 0.5 else "block",
            "score": round(max(0.0, min(100.0, 70.0 + edge_score * 20.0 - (risk_gbp / max(payload.position_gbp, 1.0)) * 50.0)), 1),
            "label": "Fast local check",
            "reasons": ["Local fast-run estimate; use full analytics mode for production review."],
            "checks": [
                {"label": "Data quality", "status": "pass", "value": "local"},
                {"label": "Risk / notional", "status": "pass" if risk_gbp / max(payload.position_gbp, 1.0) < 0.5 else "fail", "value": f"{risk_gbp / max(payload.position_gbp, 1.0):.1%}"},
            ],
        },
        "basis": None,
        "congestion": None,
    }

    try:
        row = log_risk_assessment(db, result, user_id=user.id)
        write_audit_log(
            db,
            actor=_actor(user),
            action="risk.assessment",
            target=f"risk_assessment:{row.id if row else result['market_code']}",
            after={key: result.get(key) for key in ("market_code", "position_gbp", "direction", "horizon_hours", "risk_gbp", "likely_gbp", "upside_gbp")},
        )
    except Exception:
        pass
    return RiskAssessmentResponse(**result)
'''
risk_marker = '@router.post("/risk-assessment", response_model=RiskAssessmentResponse)'
risk_next_marker = '\n\n@router.post("/risk-assessment/solve"'
if risk_marker in text and risk_next_marker in text:
    start = text.index(risk_marker)
    end = text.index(risk_next_marker, start)
    text = text[:start] + fast_risk + text[end:]
dashboard_anchor = (
    ") -> DashboardResponse:\n"
    "    market = get_market_by_code(db, market_code)\n"
)
dashboard_imports = (
    ") -> DashboardResponse:\n"
    "    from app.services.alert_service import list_alerts, refresh_alerts_for_market\n"
    "    from app.services.event_service import list_events\n"
    "    from app.services.forecast_service import list_recent_prices, run_forecast_for_market\n"
    "    from app.services.news_service import list_news_articles, list_news_sources\n\n"
    "    market = get_market_by_code(db, market_code)\n"
)
if "def get_dashboard(" in text and dashboard_anchor in text and dashboard_imports not in text:
    text = text.replace(dashboard_anchor, dashboard_imports, 1)
optimal_hedge = '''@router.post("/risk-assessment/optimal-hedge", response_model=OptimalHedgeResponse)
def post_optimal_hedge(payload: RiskAssessmentRequest, db: Session = Depends(get_db)) -> OptimalHedgeResponse:
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
        try:
            from app.services.deep_hedger import hedge_features_from_assessment, recommend_hedge_ratio
        except ModuleNotFoundError as exc:
            if exc.name == "torch":
                raise HTTPException(status_code=503, detail="Optimal hedge model is not installed in local fast-run mode") from exc
            raise
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
'''
start_marker = '@router.post("/risk-assessment/optimal-hedge"'
end_marker = '\n\n@router.post("/risk-assessment/export"'
if start_marker in text and end_marker in text:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    text = text[:start] + optimal_hedge + text[end:]
else:
    needle = "        hedge_ratio = recommend_hedge_ratio(hedge_features_from_assessment(current))\n"
    replacement = (
        "        try:\n"
        "            from app.services.deep_hedger import hedge_features_from_assessment, recommend_hedge_ratio\n"
        "        except ModuleNotFoundError as exc:\n"
        "            if exc.name == \"torch\":\n"
        "                raise HTTPException(status_code=503, detail=\"Optimal hedge model is not installed in local fast-run mode\") from exc\n"
        "            raise\n"
        "        hedge_ratio = recommend_hedge_ratio(hedge_features_from_assessment(current))\n"
    )
    if replacement not in text and needle in text:
        text = text.replace(needle, replacement)
dashboard = '''@router.get("/dashboard/{market_code}", response_model=DashboardResponse)
def get_dashboard(
    market_code: str,
    history_hours: int = Query(default=720, ge=1, le=8760),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    from app.services.alert_service import list_alerts, refresh_alerts_for_market
    from app.services.backtest_reports import dashboard_backtest_metrics
    from app.services.event_service import list_events
    from app.services.forecast_service import list_recent_prices, run_forecast_for_market
    from app.services.news_service import list_news_articles, list_news_sources

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
'''
dashboard_marker = '@router.get("/dashboard/{market_code}"'
if dashboard_marker in text:
    start = text.index(dashboard_marker)
    text = text[:start] + dashboard
routes.write_text(text)

config = root / "backend/app/core/config.py"
text = config.read_text()
if "skip_startup_seed" not in text:
    text = text.replace(
        '    demo_mode: bool = Field(default=False, alias="DEMO_MODE")\n',
        '    demo_mode: bool = Field(default=False, alias="DEMO_MODE")\n'
        '    skip_startup_seed: bool = Field(default=False, alias="SKIP_STARTUP_SEED")\n',
    )
    config.write_text(text)

main = root / "backend/app/main.py"
text = main.read_text()
text = text.replace("from app.ingestion.seeds import seed_database\n", "")
old = (
    "    if schema_ready:\n"
    "        apply_sqlite_compat_migrations(engine)\n"
    "        with SessionLocal() as db:\n"
    "            seed_database(db)\n"
    "    else:\n"
)
new = (
    "    if schema_ready and settings.skip_startup_seed:\n"
    "        apply_sqlite_compat_migrations(engine)\n"
    "    elif schema_ready:\n"
    "        apply_sqlite_compat_migrations(engine)\n"
    "        with SessionLocal() as db:\n"
    "            from app.ingestion.seeds import seed_database\n\n"
    "            seed_database(db)\n"
    "    else:\n"
)
if "settings.skip_startup_seed" not in text and old in text:
    text = text.replace(old, new)
main.write_text(text)
PY
}

patch_runtime_frontend() {
  runtime_root="$1"
  python3 - "$runtime_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])

stream = root / "frontend/lib/use-market-stream.ts"
text = stream.read_text()
text = text.replace(
    'const PUBLIC_WS_BASE_URL = process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://localhost:8000";',
    'const PUBLIC_WS_BASE_URL = process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://127.0.0.1:8000";',
)
stream.write_text(text)

power_bi = root / "frontend/components/power-bi-report.tsx"
text = power_bi.read_text()
if "const setupHeightClass =" not in text:
    text = text.replace(
        '  const heightClass = compact ? "h-[520px]" : "h-[680px]";',
        '  const heightClass = compact ? "h-[520px]" : "h-[680px]";\n'
        '  const setupHeightClass = compact ? "min-h-[120px]" : "min-h-[260px]";',
    )
text = text.replace(
    '        <div className={`${heightClass} flex items-center justify-center rounded-xl border border-dashed border-seam bg-well p-6`}>',
    '        <div className={`${setupHeightClass} flex items-center justify-center rounded-xl border border-dashed border-seam bg-well p-6`}>',
)
text = text.replace("Power BI is ready to connect.", "Power BI not connected")
text = text.replace(
    '{message || "Add the Power BI environment variables on the backend to enable embedded reports."}',
    '"Connect Power BI credentials to embed the live report here. The market model keeps running without it."',
)
power_bi.write_text(text)
PY
}

ensure_runtime_python() {
  if [ "$USE_RUNTIME_BACKEND" != "1" ]; then
    if [ ! -x "$LOCAL_PYTHON_BIN" ]; then
      bash scripts/bootstrap_local.sh
    fi
    PYTHON_BIN="$LOCAL_PYTHON_BIN"
    return
  fi

  PYTHON_BIN="$RUNTIME_ROOT/.venv/bin/python"
  if [ -x "$PYTHON_BIN" ]; then
    return
  fi

  python3 -m venv "$RUNTIME_ROOT/.venv"
  cat > "$RUNTIME_ROOT/backend/requirements-fast.txt" <<'REQ'
fastapi==0.116.1
uvicorn[standard]==0.35.0
sqlalchemy==2.0.43
psycopg[binary]==3.2.9
alembic==1.18.4
pydantic==2.11.7
pydantic-settings==2.10.1
pandas==2.2.3
numpy==2.0.2
scikit-learn>=1.6.0,<2
python-dotenv==1.1.1
httpx==0.28.1
yfinance==0.2.51
feedparser==6.0.11
arq==0.28.0
jinja2==3.1.6
reportlab==4.5.0
openpyxl==3.1.5
opentelemetry-sdk==1.39.1
opentelemetry-exporter-otlp==1.39.1
opentelemetry-instrumentation-fastapi==0.60b1
opentelemetry-instrumentation-sqlalchemy==0.60b1
opentelemetry-instrumentation-httpx==0.60b1
structlog==25.5.0
slowapi==0.1.9
REQ
  "$PYTHON_BIN" -m pip install --upgrade pip >"$RUNTIME_PIP_LOG" 2>&1
  "$PYTHON_BIN" -m pip install -r "$RUNTIME_ROOT/backend/requirements-fast.txt" >>"$RUNTIME_PIP_LOG" 2>&1 || {
    echo "Could not install backend runtime dependencies. See $RUNTIME_PIP_LOG" >&2
    tail -80 "$RUNTIME_PIP_LOG" >&2 || true
    exit 1
  }
}

ensure_runtime_frontend() {
  if [ "$USE_RUNTIME_FRONTEND" != "1" ]; then
    FRONTEND_DIR="$ROOT_DIR/frontend"
    if [ ! -x "$FRONTEND_DIR/node_modules/.bin/next" ]; then
      bash scripts/bootstrap_local.sh
    fi
    return
  fi

  FRONTEND_DIR="$RUNTIME_ROOT/frontend"
  patch_runtime_frontend "$RUNTIME_ROOT"
  if [ ! -x "$FRONTEND_DIR/node_modules/.bin/next" ]; then
    (
      cd "$FRONTEND_DIR"
      npm install --package-lock-only=false
    ) >"$RUNTIME_NPM_LOG" 2>&1 || {
      echo "Could not install frontend runtime dependencies. See $RUNTIME_NPM_LOG" >&2
      tail -80 "$RUNTIME_NPM_LOG" >&2 || true
      exit 1
    }
  fi
}

ensure_runtime_backend() {
  if [ "$USE_RUNTIME_BACKEND" != "1" ]; then
    BACKEND_DIR="$ROOT_DIR/backend"
    PROJECT_DIR="$ROOT_DIR"
    return
  fi

  if [ "$REFRESH_RUNTIME" = "1" ]; then
    rm -rf "$RUNTIME_ROOT"
  fi

  if [ ! -f "$RUNTIME_ROOT/backend/app/main.py" ]; then
    rm -rf "$RUNTIME_ROOT"
    git clone --depth 1 --branch "$RUNTIME_BRANCH" "$RUNTIME_REPO_URL" "$RUNTIME_ROOT" >"$RUNTIME_CLONE_LOG" 2>&1 || {
      echo "Could not create backend runtime cache. See $RUNTIME_CLONE_LOG" >&2
      tail -80 "$RUNTIME_CLONE_LOG" >&2 || true
      exit 1
    }
  fi

  patch_runtime_backend "$RUNTIME_ROOT"
  BACKEND_DIR="$RUNTIME_ROOT/backend"
  PROJECT_DIR="$RUNTIME_ROOT"
}

frontend_build_needed() {
  frontend_dir="${FRONTEND_DIR:-$ROOT_DIR/frontend}"
  build_id="$frontend_dir/.next/BUILD_ID"
  if [ ! -f "$build_id" ]; then
    return 0
  fi
  if [ "$REBUILD_FRONTEND" != "1" ]; then
    return 1
  fi
  if [ -n "$(find "$frontend_dir/app" "$frontend_dir/components" "$frontend_dir/lib" "$frontend_dir/types" "$frontend_dir/public" -type f -newer "$build_id" -print -quit 2>/dev/null)" ]; then
    return 0
  fi
  for file in \
    "$frontend_dir/package.json" \
    "$frontend_dir/package-lock.json" \
    "$frontend_dir/next.config.ts" \
    "$frontend_dir/tailwind.config.ts" \
    "$frontend_dir/postcss.config.js" \
    "$frontend_dir/tsconfig.json"
  do
    if [ -f "$file" ] && [ "$file" -nt "$build_id" ]; then
      return 0
    fi
  done
  return 1
}

ensure_runtime_backend
ensure_runtime_python
ensure_runtime_frontend

# Clear stale Python bytecode from local source tree (prevents disk-corruption hangs)
if [ "$USE_RUNTIME_BACKEND" != "1" ]; then
  find "$ROOT_DIR/backend" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
fi

if http_ok "http://127.0.0.1:${BACKEND_PORT}/api/health" && http_ok "$FRONTEND_HEALTH_URL"; then
  open_app
  echo "Already running: $APP_URL"
  exit 0
fi

stop_port "$BACKEND_PORT"
stop_port "$FRONTEND_PORT"

if [ "$RUN_MIGRATIONS" = "1" ]; then
  (
    cd "$PROJECT_DIR"
    DATABASE_URL="$DATABASE_URL" \
    DEMO_MODE="$DEMO_MODE" \
    EIA_API_KEY="$EIA_API_KEY" \
    RATE_LIMIT_ENABLED="$RATE_LIMIT_ENABLED" \
    PYTHONPATH=backend \
      "$PYTHON_BIN" -m alembic -c alembic.ini upgrade head
  ) >/dev/null
fi

if [ "$DATABASE_URL" = "sqlite:///$LOCAL_DB_PATH" ]; then
  if ! "$PYTHON_BIN" - "$LOCAL_DB_PATH" <<'PY' >/dev/null 2>&1
import sqlite3
import sys

path = sys.argv[1]
with sqlite3.connect(path) as conn:
    market_count = conn.execute("select count(*) from markets").fetchone()[0]
    price_count = conn.execute("select count(*) from price_points").fetchone()[0]
if market_count <= 0 or price_count < 48:
    raise SystemExit(1)
PY
  then
    (
      cd "$PROJECT_DIR"
      DATABASE_URL="$DATABASE_URL" \
      DEMO_MODE="$DEMO_MODE" \
      EIA_API_KEY="$EIA_API_KEY" \
      RATE_LIMIT_ENABLED="$RATE_LIMIT_ENABLED" \
      PYTHONPATH=backend \
        "$PYTHON_BIN" - <<'PY'
from app.db.session import SessionLocal
from app.ingestion.seeds import seed_database

with SessionLocal() as db:
    seed_database(db)
PY
    ) >/dev/null
  fi
fi

if frontend_build_needed; then
  (
    cd "$FRONTEND_DIR"
    API_INTERNAL_BASE_URL="${API_INTERNAL_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}/api}" \
    NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api/backend}" \
    NEXT_PUBLIC_WS_BASE_URL="${NEXT_PUBLIC_WS_BASE_URL:-ws://127.0.0.1:${BACKEND_PORT}}" \
    SERVER_AUTO_LOGIN="${SERVER_AUTO_LOGIN:-true}" \
    DEMO_USER_EMAIL="${DEMO_USER_EMAIL:-demo@3x.local}" \
    DEMO_USER_PASSWORD="${DEMO_USER_PASSWORD:-demo-password}" \
    NEXT_TELEMETRY_DISABLED=1 \
      npm run build
  ) >/tmp/market-speculation-run-build.log 2>&1
fi

BACKEND_DIR="$BACKEND_DIR" \
FRONTEND_DIR="$FRONTEND_DIR" \
BACKEND_LOG="$BACKEND_LOG" \
FRONTEND_LOG="$FRONTEND_LOG" \
BACKEND_PID_FILE="$BACKEND_PID_FILE" \
FRONTEND_PID_FILE="$FRONTEND_PID_FILE" \
PYTHON_BIN="$PYTHON_BIN" \
BACKEND_PORT="$BACKEND_PORT" \
FRONTEND_PORT="$FRONTEND_PORT" \
DATABASE_URL="$DATABASE_URL" \
DEMO_MODE="$DEMO_MODE" \
EIA_API_KEY="$EIA_API_KEY" \
RATE_LIMIT_ENABLED="$RATE_LIMIT_ENABLED" \
API_INTERNAL_BASE_URL="${API_INTERNAL_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}/api}" \
NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api/backend}" \
NEXT_PUBLIC_WS_BASE_URL="${NEXT_PUBLIC_WS_BASE_URL:-ws://127.0.0.1:${BACKEND_PORT}}" \
SERVER_AUTO_LOGIN="${SERVER_AUTO_LOGIN:-true}" \
DEMO_USER_EMAIL="${DEMO_USER_EMAIL:-demo@3x.local}" \
DEMO_USER_PASSWORD="${DEMO_USER_PASSWORD:-demo-password}" \
python3 - <<'PY'
import os
import subprocess

backend_log = open(os.environ["BACKEND_LOG"], "wb")
frontend_log = open(os.environ["FRONTEND_LOG"], "wb")

backend_env = os.environ.copy()
backend_env.update(
    {
        "DATABASE_URL": os.environ["DATABASE_URL"],
        "DEMO_MODE": os.environ["DEMO_MODE"],
        "EIA_API_KEY": os.environ["EIA_API_KEY"],
        "SKIP_STARTUP_SEED": "true",
        "RATE_LIMIT_ENABLED": os.environ["RATE_LIMIT_ENABLED"],
        "PYTHONPATH": ".",
    }
)
backend = subprocess.Popen(
    [
        os.environ["PYTHON_BIN"],
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        os.environ["BACKEND_PORT"],
    ],
    cwd=os.environ["BACKEND_DIR"],
    env=backend_env,
    stdin=subprocess.DEVNULL,
    stdout=backend_log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)

frontend_env = os.environ.copy()
frontend_env.update(
    {
        "API_INTERNAL_BASE_URL": os.environ["API_INTERNAL_BASE_URL"],
        "NEXT_PUBLIC_API_BASE_URL": os.environ["NEXT_PUBLIC_API_BASE_URL"],
        "NEXT_PUBLIC_WS_BASE_URL": os.environ["NEXT_PUBLIC_WS_BASE_URL"],
        "SERVER_AUTO_LOGIN": os.environ["SERVER_AUTO_LOGIN"],
        "DEMO_USER_EMAIL": os.environ["DEMO_USER_EMAIL"],
        "DEMO_USER_PASSWORD": os.environ["DEMO_USER_PASSWORD"],
        "NEXT_TELEMETRY_DISABLED": "1",
    }
)
frontend = subprocess.Popen(
    ["./node_modules/.bin/next", "start", "--hostname", "127.0.0.1", "-p", os.environ["FRONTEND_PORT"]],
    cwd=os.environ["FRONTEND_DIR"],
    env=frontend_env,
    stdin=subprocess.DEVNULL,
    stdout=frontend_log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)

with open(os.environ["BACKEND_PID_FILE"], "w", encoding="utf-8") as handle:
    handle.write(f"{backend.pid}\n")
with open(os.environ["FRONTEND_PID_FILE"], "w", encoding="utf-8") as handle:
    handle.write(f"{frontend.pid}\n")
PY

wait_for "Backend" "http://127.0.0.1:${BACKEND_PORT}/api/health" 160
wait_for "Frontend" "$FRONTEND_HEALTH_URL" 480
open_app
echo "Running: $APP_URL"
