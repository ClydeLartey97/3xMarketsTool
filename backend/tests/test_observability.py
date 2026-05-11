from __future__ import annotations

import json
import logging

from app.core.observability import build_json_log_formatter
from app.main import app


def test_observability_instruments_fastapi_health_route(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert app.state.observability["service_name"] == "3x-api"
    assert app.state.observability["excluded_urls"] == "/api/health"
    assert getattr(app, "_is_instrumented_by_opentelemetry") is True


def test_json_log_formatter_outputs_structured_record() -> None:
    record = logging.LogRecord(
        name="observability.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="structured logging ready",
        args=(),
        exc_info=None,
    )
    payload = json.loads(build_json_log_formatter().format(record))
    assert payload["event"] == "structured logging ready"
    assert payload["level"] == "info"
    assert payload["logger"] == "observability.test"
