from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, Sum
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from skill_manager import SkillObservabilityEvent
from skill_manager.otel import OpenTelemetrySkillObservabilitySink


@pytest.mark.parametrize("owned", [True, False])
async def test_spans_metrics_and_provider_ownership(owned: bool) -> None:
    exporter = InMemorySpanExporter()
    traces = TracerProvider()
    traces.add_span_processor(SimpleSpanProcessor(exporter))
    reader = InMemoryMetricReader()
    metrics = MeterProvider(metric_readers=[reader])
    sink = OpenTelemetrySkillObservabilitySink(
        tracer_provider=traces, meter_provider=metrics, owns_providers=owned
    )
    event = SkillObservabilityEvent(name="skill.test", attributes={"count": 2})
    await sink.emit(event)
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == event.name
    assert spans[0].start_time == spans[0].end_time
    data = reader.get_metrics_data()
    assert data is not None
    metric = data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.name == "skill_manager.events"
    assert isinstance(metric.data, Sum)
    assert metric.data.data_points[0].value == 1
    await sink.aclose()
    if not owned:
        traces.shutdown()
        metrics.shutdown()


async def test_global_and_explicit_instrumentation() -> None:
    sink = OpenTelemetrySkillObservabilitySink()
    await sink.emit(SkillObservabilityEvent(name="skill.global"))
    await sink.aclose()
    traces = TracerProvider()
    metrics = MeterProvider()
    sink = OpenTelemetrySkillObservabilitySink(
        traces.get_tracer("test"), meter=metrics.get_meter("test")
    )
    await sink.aclose()
    traces.shutdown()
    metrics.shutdown()
