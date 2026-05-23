from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MarketBase(BaseModel):
    name: str
    code: str
    commodity_type: str
    region: str
    timezone: str
    data_status: str = "ready"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketRead(MarketBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class PricePointRead(BaseModel):
    id: int
    market_id: int
    timestamp: datetime
    horizon_type: str
    price_value: float
    currency: str = "USD"
    source: str

    model_config = ConfigDict(from_attributes=True)


class MarketTimeseriesPoint(BaseModel):
    timestamp: datetime
    demand_mw: Optional[float] = None
    wind_mw: Optional[float] = None
    solar_mw: Optional[float] = None
    wind_share: Optional[float] = None
    solar_share: Optional[float] = None


class WeatherPointRead(BaseModel):
    id: int
    market_id: int
    timestamp: datetime
    temperature_c: float
    wind_speed: float
    wind_generation_estimate: float
    solar_generation_estimate: float
    precipitation: float
    source: str

    model_config = ConfigDict(from_attributes=True)


class DemandPointRead(BaseModel):
    id: int
    market_id: int
    timestamp: datetime
    demand_mw: float
    source: str

    model_config = ConfigDict(from_attributes=True)


class ArticleIngestRequest(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    published_at: datetime
    market_code: Optional[str] = None


class NewsArticleRead(BaseModel):
    id: int
    market_id: Optional[int]
    market_code: Optional[str]
    title: str
    display_title: str
    summary: str
    display_summary: str
    source_name: str
    source_url: str
    source_language: str
    is_auto_translated: bool
    credibility_rating: float
    credibility_label: str
    published_at: datetime
    event_type: Optional[str]
    price_direction: Optional[str]
    affected_region: Optional[str]


class NewsSourceRead(BaseModel):
    key: str
    name: str
    url: str
    language: str
    country: str
    coverage: list[str]
    credibility_rating: float
    credibility_label: str
    notes: str


class EventRead(BaseModel):
    id: int
    article_id: Optional[int]
    market_id: Optional[int]
    event_type: str
    title: str
    description: str
    affected_region: str
    asset_type: str
    capacity_impact_mw: Optional[float]
    zone: Optional[str] = None
    node: Optional[str] = None
    magnitude_mw: Optional[float] = None
    duration_hours_estimate: Optional[float] = None
    duration_hours_p10: Optional[float] = None
    duration_hours_p90: Optional[float] = None
    analogue_event_ids: list[int] = Field(default_factory=list)
    classifier_version: str = "heuristic-v1"
    start_time: Optional[datetime]
    expected_end_time: Optional[datetime]
    severity: str
    confidence: float
    price_direction: str
    estimated_price_impact_pct: Optional[float]
    rationale: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertRead(BaseModel):
    id: int
    market_id: int
    alert_type: str
    title: str
    body: str
    severity: str
    created_at: datetime
    is_read: bool

    model_config = ConfigDict(from_attributes=True)


class ForecastRead(BaseModel):
    id: int
    market_id: int
    forecast_for_timestamp: datetime
    generated_at: datetime
    point_estimate: float
    lower_bound: float
    upper_bound: float
    currency: str = "USD"
    spike_probability: float
    model_version: str
    rationale_summary: str
    feature_snapshot_json: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class ForecastRunResponse(BaseModel):
    market: MarketRead
    forecast_points: list[ForecastRead]
    metrics: dict[str, float]


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database: str


class PowerBIReportTarget(BaseModel):
    workspace_id: str
    report_id: str
    dataset_id: Optional[str] = None
    page_name: Optional[str] = None


class PowerBIEmbedConfig(BaseModel):
    enabled: bool
    configured: bool
    market_code: Optional[str] = None
    workspace_id: Optional[str] = None
    report_id: Optional[str] = None
    dataset_id: Optional[str] = None
    report_name: Optional[str] = None
    embed_url: Optional[str] = None
    embed_token: Optional[str] = None
    token_type: Literal["Embed"] = "Embed"
    expires_at: Optional[datetime] = None
    page_name: Optional[str] = None
    filter_table: Optional[str] = None
    filter_column: Optional[str] = None
    reason: Optional[str] = None


class UserRead(BaseModel):
    id: int
    email: str
    organisation: str
    role: str
    created_at: datetime


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=1, max_length=256)


class AuthRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=8, max_length=256)
    organisation: str = Field(default="3x", min_length=1, max_length=128)
    role: str = Field(default="analyst", min_length=1, max_length=64)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserRead


class AuditLogRead(BaseModel):
    id: int
    created_at: datetime
    actor: str
    action: str
    target: str
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    signed_hash: str


class ScenarioOverride(BaseModel):
    """One named what-if shock to the simulator inputs."""
    name: str
    sigma_multiplier: float = 1.0          # widen/narrow vol
    drift_shift: float = 0.0                # log-return drift add per hour
    spot_shock_pct: float = 0.0             # one-shot % move at t=0


class RiskAssessmentRequest(BaseModel):
    market_code: str
    position_gbp: float = Field(default=10000.0, gt=0)
    position_unit: Literal["GBP", "MWh"] = "GBP"
    position_mwh: Optional[float] = Field(default=None, gt=0)
    hedge_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    direction: str = Field(default="long", pattern="^(long|short)$")
    target_timestamp: Optional[datetime] = None
    scenarios: list[ScenarioOverride] = Field(default_factory=list)
    n_paths: int = Field(default=5000, ge=500, le=20000)
    # E.3 — cross-zone basis trades. When `basis_against_market_code` is
    # set, the simulator runs paired paths against the second market and
    # P&L is the spread (with `basis_direction` applied to the spread).
    basis_against_market_code: Optional[str] = None
    basis_direction: Literal["long", "short"] = "long"


class RiskSolveRequest(BaseModel):
    market_code: str
    max_risk_gbp: float = Field(gt=0)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    direction: Literal["long", "short"] = "long"
    position_unit: Literal["GBP", "MWh"] = "GBP"
    target_timestamp: Optional[datetime] = None


class ScenarioOutcome(BaseModel):
    name: str
    risk_gbp: float
    likely_gbp: float
    upside_gbp: float
    prob_loss: float


class CoefficientItem(BaseModel):
    """A single transparent input/parameter that drives a risk number.

    Every coefficient that goes into the three headline numbers is exposed
    here so traders / analysts can audit exactly how a result was built.
    """
    key: str                          # programmatic id (e.g. "sigma_hourly")
    label: str                        # human label ("Hourly σ (log-return)")
    value: float                      # current numeric value
    unit: str                         # "%", "£", "log-return", "ratio", ...
    group: str                        # "forecast" | "realised_vol" | "llm" | "fx" | "position" | "result"
    description: str                  # one-line plain-English explanation


class CoefficientBlock(BaseModel):
    """All coefficients grouped + a brief equation summary."""
    items: list[CoefficientItem] = Field(default_factory=list)
    equation_summary: str = ""


class DecisionGate(BaseModel):
    action: Literal["clear", "watch", "block"]
    score: float
    label: str
    reasons: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)


class RiskAssessmentResponse(BaseModel):
    market_code: str
    market_name: str
    as_of: datetime
    position_gbp: float
    direction: str
    horizon_hours: int
    target_timestamp: datetime
    spot_price: float
    forecast_price: float
    expected_price: float
    sigma_price: float
    sigma_hourly_pct: float
    expected_return_pct: float
    sigma_return_pct: float
    risk_gbp: float
    likely_gbp: float
    upside_gbp: float
    risk_metric: str = "cvar_95_normal"
    var95_gbp: float
    prob_loss: float = 0.0
    max_drawdown_gbp: float = 0.0
    fx_to_gbp: float = 1.0
    price_currency: str = "USD"
    n_paths: int = 0
    edge_score: float
    confidence: float
    regime: str
    catalyst_severity: float
    asymmetry: float
    tail_multiplier: float
    scorer_provider: str
    rationale: str
    scenarios: list[ScenarioOutcome] = Field(default_factory=list)
    coefficients: CoefficientBlock = Field(default_factory=CoefficientBlock)
    decision_gate: DecisionGate
    basis: Optional[dict[str, Any]] = None
    congestion: Optional[dict[str, Any]] = None


class RiskSolveResponse(BaseModel):
    max_risk_gbp: float
    achieved_risk_gbp: float
    risk_error_pct: float
    tolerance_pct: float
    iterations: int
    converged: bool
    resolved_request: RiskAssessmentRequest
    assessment: RiskAssessmentResponse


SensitivityCoefficient = Literal[
    "tail_multiplier",
    "asymmetry",
    "catalyst_severity",
    "sigma_hourly",
    "drift_hourly",
    "fx_to_gbp",
    "hedge_ratio",
]


class RiskSensitivityRequest(RiskAssessmentRequest):
    coefficients_to_perturb: list[SensitivityCoefficient] = Field(default_factory=list)


class RiskSensitivityCell(BaseModel):
    perturbation_pct: float
    risk_gbp: float
    likely_gbp: float
    upside_gbp: float


class RiskSensitivityRow(BaseModel):
    coefficient: SensitivityCoefficient
    base_value: float
    cells: list[RiskSensitivityCell]


class RiskSensitivityResponse(BaseModel):
    market_code: str
    position_gbp: float
    direction: str
    horizon_hours: int
    perturbations_pct: list[float]
    rows: list[RiskSensitivityRow]


class RiskCalibrationResponse(BaseModel):
    market_id: int
    claimed_breach_rate: float = 0.05
    actual_breach_rate: float
    kupiec_p_value: float
    sample_count: int
    calibration_status: Literal["honest", "understating", "overstating"]


class DecisionCreateRequest(BaseModel):
    market_code: str
    position_gbp: float = Field(gt=0)
    direction: Literal["long", "short"]
    horizon_hours: int = Field(ge=1, le=168)
    risk_gbp: float
    likely_gbp: float
    upside_gbp: float
    thesis_text: str = Field(min_length=1, max_length=4_000)
    is_open: bool = True


class DecisionUpdateRequest(BaseModel):
    thesis_text: Optional[str] = Field(default=None, min_length=1, max_length=4_000)
    is_open: Optional[bool] = None


class DecisionRead(BaseModel):
    id: int
    timestamp: datetime
    market_id: int
    market_code: str
    market_name: str
    user_id: Optional[int] = None
    position_gbp: float
    direction: str
    horizon_hours: int
    risk_gbp: float
    likely_gbp: float
    upside_gbp: float
    realized_pnl_gbp: Optional[float]
    predicted_percentile: Optional[float]
    thesis_text: str
    is_open: bool
    closed_at: Optional[datetime]


class RiskPathFanResponse(BaseModel):
    market_code: str
    horizon_hours: int
    path_hours: list[int]
    price_paths: list[list[float]]
    assessment: RiskAssessmentResponse


class PortfolioPositionRequest(BaseModel):
    market_code: str
    position_gbp: float = Field(gt=0)
    direction: Literal["long", "short"] = "long"


class PortfolioRiskRequest(BaseModel):
    positions: list[PortfolioPositionRequest] = Field(min_length=1)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    n_paths: int = Field(default=5000, ge=500, le=20000)


class PortfolioRiskContribution(BaseModel):
    market_code: str
    position_gbp: float
    direction: str
    standalone_risk_gbp: float
    standalone_likely_gbp: float
    standalone_upside_gbp: float
    simulated_risk_gbp: float
    risk_contribution_gbp: float


class PortfolioRiskResponse(BaseModel):
    portfolio_risk_gbp: float
    portfolio_likely_gbp: float
    portfolio_upside_gbp: float
    var95_gbp: float
    prob_loss: float
    sum_standalone_risk_gbp: float
    horizon_hours: int
    n_paths: int
    correlation_source: str
    contributions: list[PortfolioRiskContribution]


class OptimalHedgeResponse(BaseModel):
    market_code: str
    hedge_ratio: float
    unhedged_ratio: float
    risk_before_gbp: float
    risk_after_gbp: float
    likely_cost_gbp: float
    current_assessment: RiskAssessmentResponse
    hedged_assessment: RiskAssessmentResponse


class DashboardResponse(BaseModel):
    market: MarketRead
    latest_forecast: Optional[ForecastRead]
    forecasts: list[ForecastRead]
    recent_prices: list[PricePointRead]
    recent_events: list[EventRead]
    recent_news: list[NewsArticleRead]
    tracked_sources: list[NewsSourceRead]
    active_alerts: list[AlertRead]
    key_metrics: dict[str, float]
