from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "3x API"
    environment: str = "development"
    api_v1_prefix: str = "/api"
    database_url: str = Field(
        default="sqlite:///./threex.db",
        alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        alias="CORS_ORIGINS",
    )
    default_market_code: str = "ERCOT_NORTH"
    default_timezone: str = "America/Chicago"
    seed_days: int = 14

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
