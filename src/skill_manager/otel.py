"""OpenTelemetry observability sink.

Install with ``pip install 'skill-manager[otel]'``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skill_manager._optional import optional_import
from skill_manager.observability import SkillObservabilityEvent, SkillObservabilitySink

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.trace import Tracer

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)


def _nanoseconds(moment: datetime) -> int:
    return (moment - _EPOCH) // _MICROSECOND * 1_000


class OpenTelemetrySkillObservabilitySink(SkillObservabilitySink):
    """Emit each Skill event as an OpenTelemetry span and count it as a metric.

    Each event becomes a zero-duration span named after the event, stamped with
    its time and attributes, and created with ``tracer.start_span`` so the
    current span context never changes; the span's parent is the span current
    at emit time. The ``skill_manager.events`` counter is incremented with an
    ``event.name`` attribute.

    Pass SDK providers to let the sink flush them on `aclose`; set
    ``owns_providers=True`` to shut them down instead. Without providers or an
    explicit tracer and meter, the global providers are used and never flushed
    or shut down by the sink.

    Args:
        tracer: Tracer to create spans with.
        meter: Meter to create the event counter with.
        tracer_provider: SDK tracer provider, used when ``tracer`` is omitted.
        meter_provider: SDK meter provider, used when ``meter`` is omitted.
        instrumentation_name: Tracer and meter name.
        owns_providers: Shut the given providers down in `aclose`.
    """

    def __init__(
        self,
        tracer: Tracer | None = None,
        *,
        meter: Meter | None = None,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        instrumentation_name: str = "skill_manager",
        owns_providers: bool = False,
    ) -> None:
        if tracer is None:
            tracer = (
                tracer_provider.get_tracer(instrumentation_name)
                if tracer_provider is not None
                else optional_import("opentelemetry.trace", "otel").get_tracer(instrumentation_name)
            )
        if meter is None:
            meter = (
                meter_provider.get_meter(instrumentation_name)
                if meter_provider is not None
                else optional_import("opentelemetry.metrics", "otel").get_meter(
                    instrumentation_name
                )
            )
        self.tracer: Tracer = tracer
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider
        self.owns_providers = owns_providers
        self._counter = meter.create_counter(
            "skill_manager.events", unit="{event}", description="Skill lifecycle events"
        )

    async def emit(self, event: SkillObservabilityEvent) -> None:
        """Record ``event`` as a span and a counter increment."""
        timestamp = _nanoseconds(event.occurred_at)
        span = self.tracer.start_span(
            event.name, attributes=dict(event.attributes), start_time=timestamp
        )
        span.end(end_time=timestamp)
        self._counter.add(1, {"event.name": event.name})

    async def aclose(self) -> None:
        """Flush, or shut down when owned, the configured providers."""
        for provider in (self.tracer_provider, self.meter_provider):
            if provider is not None:
                await asyncio.to_thread(_close, provider, shutdown=self.owns_providers)


def _close(provider: TracerProvider | MeterProvider, *, shutdown: bool) -> None:
    if shutdown:
        provider.shutdown()
    else:
        provider.force_flush()


__all__ = ["OpenTelemetrySkillObservabilitySink"]
