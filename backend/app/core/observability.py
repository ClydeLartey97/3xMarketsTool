from __future__ import annotations

import logging
from typing import Any

import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from sqlalchemy.engine import Engine

from app.core.config import Settings

_LOGGING_CONFIGURED = False
_TRACING_CONFIGURED = False
_HTTPX_INSTRUMENTED = False
_SQLALCHEMY_INSTRUMENTED = False
_FASTAPI_INSTRUMENTED_APPS: set[int] = set()


def _add_trace_context(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = f"{span_context.trace_id:032x}"
        event_dict["span_id"] = f"{span_context.span_id:016x}"
    return event_dict


def _shared_log_processors() -> list[Any]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_trace_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def build_json_log_formatter() -> structlog.stdlib.ProcessorFormatter:
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_log_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )


def configure_logging(settings: Settings) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            *_shared_log_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(build_json_log_formatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "apscheduler"):
        logging.getLogger(logger_name).setLevel(level)

    _LOGGING_CONFIGURED = True


def _configure_tracing(settings: Settings) -> None:
    global _TRACING_CONFIGURED
    if _TRACING_CONFIGURED:
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _TRACING_CONFIGURED = True


def instrument_app(app: FastAPI, engine: Engine, settings: Settings) -> None:
    global _HTTPX_INSTRUMENTED, _SQLALCHEMY_INSTRUMENTED

    _configure_tracing(settings)
    app_id = id(app)
    if app_id not in _FASTAPI_INSTRUMENTED_APPS:
        FastAPIInstrumentor.instrument_app(app, excluded_urls=settings.otel_excluded_urls)
        _FASTAPI_INSTRUMENTED_APPS.add(app_id)

    if not _SQLALCHEMY_INSTRUMENTED:
        SQLAlchemyInstrumentor().instrument(engine=engine)
        _SQLALCHEMY_INSTRUMENTED = True

    if not _HTTPX_INSTRUMENTED:
        HTTPXClientInstrumentor().instrument()
        _HTTPX_INSTRUMENTED = True

    app.state.observability = {
        "service_name": settings.otel_service_name,
        "otlp_enabled": bool(settings.otel_exporter_otlp_endpoint),
        "excluded_urls": settings.otel_excluded_urls,
    }
