"""Export Skill traces and metrics through an injected OTel SDK."""

import asyncio
import os

from _shared import sample_skill, show
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from skill_manager import SkillManager
from skill_manager.otel import OpenTelemetrySkillObservabilitySink


async def main() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318").rstrip("/")
    resource = Resource.create({"service.name": "skill-manager-example"})
    traces = TracerProvider(resource=resource)
    traces.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    metrics = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"))
        ],
    )
    sink = OpenTelemetrySkillObservabilitySink(
        tracer_provider=traces, meter_provider=metrics, owns_providers=True
    )
    try:
        async with SkillManager(observability_sink=sink) as manager:
            await manager.register_skill(sample_skill())
            await manager.discover("ticket")
            await manager.build_bundle(["summarize-ticket"])
    finally:
        await sink.aclose()
    show("OTel export complete", {"endpoint": endpoint, "service": "skill-manager-example"})


if __name__ == "__main__":
    asyncio.run(main())
