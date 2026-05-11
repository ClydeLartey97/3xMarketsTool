from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "3x API"
    environment: str = "development"
    api_v1_prefix: str = "/api"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/threex",
        alias="DATABASE_URL",
    )
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
    active_forecaster: str = Field(default="gbr", alias="ACTIVE_FORECASTER")
    chronos_use_small: bool = Field(default=False, alias="CHRONOS_USE_SMALL")
    chronos_device_map: str = Field(default="cpu", alias="CHRONOS_DEVICE_MAP")
    llm_scorer_provider: str = Field(default="heuristic", alias="LLM_SCORER_PROVIDER")
    domain_scorer_model_dir: str = Field(default="models/news_scorer_lora", alias="DOMAIN_SCORER_MODEL_DIR")
    domain_scorer_base_model: str = Field(
        default="meta-llama/Llama-3.1-8B-Instruct",
        alias="DOMAIN_SCORER_BASE_MODEL",
    )
    domain_scorer_device_map: str = Field(default="auto", alias="DOMAIN_SCORER_DEVICE_MAP")
    jwt_secret: SecretStr = Field(default=SecretStr("dev-change-me"), alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=12 * 60, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    demo_user_email: str = Field(default="demo@3x.local", alias="DEMO_USER_EMAIL")
    demo_user_password: str = Field(default="demo-password", alias="DEMO_USER_PASSWORD")

    # Background refresh interval in minutes
    data_refresh_interval_minutes: int = Field(default=30, alias="DATA_REFRESH_INTERVAL_MINUTES")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
