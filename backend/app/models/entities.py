from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    commodity_type: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    price_points: Mapped[list["PricePoint"]] = relationship(back_populates="market")
    weather_points: Mapped[list["WeatherPoint"]] = relationship(back_populates="market")
    demand_points: Mapped[list["DemandPoint"]] = relationship(back_populates="market")
    events: Mapped[list["Event"]] = relationship(back_populates="market")
    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="market")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="market")
    risk_assessment_logs: Mapped[list["RiskAssessmentLog"]] = relationship(back_populates="market")


class PricePoint(Base):
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon_type: Mapped[str] = mapped_column(String(32), default="spot")
    price_value: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    source: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    market: Mapped["Market"] = relationship(back_populates="price_points")


class WeatherPoint(Base):
    __tablename__ = "weather_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    temperature_c: Mapped[float] = mapped_column(Float)
    wind_speed: Mapped[float] = mapped_column(Float)
    wind_generation_estimate: Mapped[float] = mapped_column(Float)
    solar_generation_estimate: Mapped[float] = mapped_column(Float)
    precipitation: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    market: Mapped["Market"] = relationship(back_populates="weather_points")


class DemandPoint(Base):
    __tablename__ = "demand_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    demand_mw: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    market: Mapped["Market"] = relationship(back_populates="demand_points")


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(512))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    processed_status: Mapped[str] = mapped_column(String(64), default="pending")

    events: Mapped[list["Event"]] = relationship(back_populates="article")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[Optional[int]] = mapped_column(ForeignKey("news_articles.id"), nullable=True)
    market_id: Mapped[Optional[int]] = mapped_column(ForeignKey("markets.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    affected_region: Mapped[str] = mapped_column(String(128))
    asset_type: Mapped[str] = mapped_column(String(64))
    capacity_impact_mw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    node: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    magnitude_mw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_hours_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_hours_p10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_hours_p90: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    analogue_event_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    classifier_version: Mapped[str] = mapped_column(String(64), default="heuristic-v2")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    severity: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    price_direction: Mapped[str] = mapped_column(String(32))
    estimated_price_impact_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    article: Mapped["NewsArticle"] = relationship(back_populates="events")
    market: Mapped[Optional["Market"]] = relationship(back_populates="events")


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    forecast_for_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    point_estimate: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[float] = mapped_column(Float)
    upper_bound: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    spike_probability: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(64))
    rationale_summary: Mapped[str] = mapped_column(Text)
    feature_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)

    market: Mapped["Market"] = relationship(back_populates="forecasts")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    market: Mapped["Market"] = relationship(back_populates="alerts")


class RiskAssessmentLog(Base):
    __tablename__ = "risk_assessment_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    position_gbp: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(16))
    horizon_hours: Mapped[int] = mapped_column(Integer)
    risk_gbp: Mapped[float] = mapped_column(Float)
    likely_gbp: Mapped[float] = mapped_column(Float)
    upside_gbp: Mapped[float] = mapped_column(Float)
    realized_pnl_gbp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="auto", index=True)
    thesis_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    market: Mapped["Market"] = relationship(back_populates="risk_assessment_logs")
    user: Mapped[Optional["User"]] = relationship(back_populates="risk_assessment_logs")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(256), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    organisation: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    watchlists: Mapped[list["UserWatchlist"]] = relationship(back_populates="user")
    risk_assessment_logs: Mapped[list["RiskAssessmentLog"]] = relationship(back_populates="user")


class UserWatchlist(Base):
    __tablename__ = "user_watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    configuration_json: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship(back_populates="watchlists")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(256), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str] = mapped_column(String(256), index=True)
    before_json: Mapped[Optional[dict]] = mapped_column("before", JSON, nullable=True)
    after_json: Mapped[Optional[dict]] = mapped_column("after", JSON, nullable=True)
    signed_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
