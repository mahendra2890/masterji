"""OpenTelemetry setup, mirroring Teotia-Sons/transcriber's tracing.py.

No-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set, so local dev and tests pay
nothing. In prod, Django/psycopg/requests are auto-instrumented and the
coach app opens one business-level span per user operation (coach.turn).
"""

from django.conf import settings


def setup_tracing() -> None:
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": "masterji-api"})
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces",
                headers={"x-api-key": settings.OTEL_EXPORTER_OTLP_API_KEY},
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    DjangoInstrumentor().instrument()
    PsycopgInstrumentor().instrument()
    RequestsInstrumentor().instrument()
