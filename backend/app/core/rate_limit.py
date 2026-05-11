from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.services.auth import decode_access_token


def rate_limit_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = decode_access_token(token)
            if payload.get("sub"):
                return f"user:{payload['sub']}"
        except HTTPException:
            pass
    return get_remote_address(request)


settings = get_settings()
RISK_ASSESSMENT_LIMIT = f"{settings.rate_limit_risk_assessment_per_minute}/minute"
SENSITIVITY_LIMIT = f"{settings.rate_limit_sensitivity_per_minute}/minute"
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[f"{settings.rate_limit_data_per_minute}/minute"],
    headers_enabled=True,
    enabled=settings.rate_limit_enabled,
)


def configure_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
