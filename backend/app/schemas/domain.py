from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class MarketBase(BaseModel):
    name: str
    code: str
    commodity_type: str
    region: str
    timezone: str
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
    source: str

    model_config = ConfigDict(from_attributes=True)


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


class DashboardResponse(BaseModel):
    market: MarketRead
    latest_forecast: Optional[ForecastRead]
    forecasts: list[ForecastRead]
    recent_prices: list[PricePointRead]
    recent_events: list[EventRead]
    active_alerts: list[AlertRead]
    key_metrics: dict[str, float]
