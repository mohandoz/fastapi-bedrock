"""OpenTelemetry wiring: traces + metrics + logs exported via OTLP.

Enabled with ``OTEL_ENABLED=true`` and pointed at an OTLP endpoint (the bundled
``grafana/otel-lgtm`` at http://otel-lgtm:4318 in compose). Default protocol is
http/protobuf, so per-signal paths are appended. Kept explicit and typed to
match the template's no-magic style.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
{%- if cookiecutter.use_http_client == "yes" %}
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
{%- endif %}
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import engine


def configure_observability(app: FastAPI) -> None:
    """Set up OTLP exporters and instrument the app.

    Call INSIDE the lifespan, AFTER ``configure_logging()`` — that function
    reassigns ``root.handlers``, which would otherwise drop the OTLP log handler
    appended here.
    """
    if not settings.otel_enabled:
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.version,
            "deployment.environment": settings.environment,
        }
    )
    base = settings.otel_exporter_otlp_endpoint.rstrip("/")

    # --- Traces -> Tempo ---
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics -> Prometheus ---
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"))],
    )
    metrics.set_meter_provider(meter_provider)

    # --- Logs -> Loki (bridge the stdlib root logger; keeps the structlog stream) ---
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs"))
    )
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    )

    # --- Instrumentation ---
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,  # async engines REQUIRE .sync_engine
        enable_commenter=True,
    )
{%- if cookiecutter.use_http_client == "yes" %}
    HTTPXClientInstrumentor().instrument()  # propagate trace context on outbound calls
{%- endif %}

    app.state.tracer_provider = tracer_provider
    app.state.meter_provider = meter_provider
    app.state.logger_provider = logger_provider


def shutdown_observability(app: FastAPI) -> None:
    """Flush and stop the exporters on shutdown."""
    for name in ("tracer_provider", "meter_provider", "logger_provider"):
        provider = getattr(app.state, name, None)
        if provider is not None:
            provider.shutdown()
