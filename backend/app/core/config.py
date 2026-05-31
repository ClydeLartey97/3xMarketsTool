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
    skip_startup_seed: bool = Field(default=False, alias="SKIP_STARTUP_SEED")

    # Real data API keys (optional — app degrades gracefully without them)
    eia_api_key: str = Field(default="", alias="EIA_API_KEY")

    # Optional Power BI embedded analytics configuration.
    power_bi_tenant_id: str = Field(default="", alias="POWER_BI_TENANT_ID")
    power_bi_client_id: str = Field(default="", alias="POWER_BI_CLIENT_ID")
    power_bi_client_secret: SecretStr = Field(default=SecretStr(""), alias="POWER_BI_CLIENT_SECRET")
    power_bi_workspace_id: str = Field(default="", alias="POWER_BI_WORKSPACE_ID")
    power_bi_report_id: str = Field(default="", alias="POWER_BI_REPORT_ID")
    power_bi_dataset_id: str = Field(default="", alias="POWER_BI_DATASET_ID")
    power_bi_report_map_json: str = Field(default="", alias="POWER_BI_REPORT_MAP_JSON")
    power_bi_market_filter_table: str = Field(default="", alias="POWER_BI_MARKET_FILTER_TABLE")
    power_bi_market_filter_column: str = Field(default="", alias="POWER_BI_MARKET_FILTER_COLUMN")

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
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    otel_service_name: str = Field(default="3x-api", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_console_exporter: bool = Field(default=False, alias="OTEL_CONSOLE_EXPORTER")
    otel_excluded_urls: str = Field(default="/api/health", alias="OTEL_EXCLUDED_URLS")
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_data_per_minute: int = Field(default=60, alias="RATE_LIMIT_DATA_PER_MINUTE")
    rate_limit_risk_assessment_per_minute: int = Field(default=10, alias="RATE_LIMIT_RISK_ASSESSMENT_PER_MINUTE")
    rate_limit_sensitivity_per_minute: int = Field(default=5, alias="RATE_LIMIT_SENSITIVITY_PER_MINUTE")
    allow_registration: bool = Field(default=False, alias="ALLOW_REGISTRATION")
    registration_default_role: str = Field(default="analyst", alias="REGISTRATION_DEFAULT_ROLE")
    audit_export_roles: list[str] = Field(
        default_factory=lambda: ["admin", "auditor"],
        alias="AUDIT_EXPORT_ROLES",
    )

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


def validate_runtime_settings(settings: Settings) -> None:
    """Fail fast for production deployments with development-safe defaults."""
    if settings.environment.lower() not in {"production", "prod"}:
        return

    jwt_secret = settings.jwt_secret.get_secret_value()
    if jwt_secret in {"dev-change-me", "change-me-in-production"} or len(jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must be set to a strong secret in production.")
    if settings.demo_user_password == "demo-password":
        raise RuntimeError("DEMO_USER_PASSWORD must be changed in production.")
    if "*" in settings.cors_origins:
        raise RuntimeError("CORS_ORIGINS must not contain '*' in production.")
