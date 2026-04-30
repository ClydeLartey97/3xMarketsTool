from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "3x API"
    environment: str = "development"
    api_v1_prefix: str = "/api"
    database_url: str = Field(default="sqlite:///./threex.db", alias="DATABASE_URL")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        alias="CORS_ORIGINS",
    )
    default_market_code: str = "ERCOT_NORTH"
    default_timezone: str = "America/Chicago"
    seed_days: int = 14
    demo_mode: bool = Field(default=False, alias="DEMO_MODE")

    # Real data API keys (optional — app degrades gracefully without them)
    eia_api_key: str = Field(default="", alias="EIA_API_KEY")

    # Forecast cache TTL in minutes
    forecast_cache_ttl_minutes: int = Field(default=15, alias="FORECAST_CACHE_TTL_MINUTES")

    # Background refresh interval in minutes
    data_refresh_interval_minutes: int = Field(default=30, alias="DATA_REFRESH_INTERVAL_MINUTES")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
