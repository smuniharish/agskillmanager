"""Provider-neutral observability events for the Skill domain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

type SkillObservabilityValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class SkillObservabilityEvent:
    """One sanitized Skill lifecycle event.

    Attributes:
        name: Dotted event name, for example ``skill.registered``.
        occurred_at: Timezone-aware time the event happened.
        attributes: Scalar, non-secret event attributes.
    """

    name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    attributes: Mapping[str, SkillObservabilityValue] = field(default_factory=dict)


class SkillObservabilitySink(ABC):
    """Application-owned destination for Skill lifecycle telemetry.

    `SkillManager` awaits `emit` after each lifecycle operation. A failing sink
    never interrupts the operation; the error is kept on
    `SkillManager.observability_errors`.

    Example:
        ```python
        class LoggingSink(SkillObservabilitySink):
            async def emit(self, event):
                logger.info(event.name, extra=dict(event.attributes))
        ```
    """

    @abstractmethod
    async def emit(self, event: SkillObservabilityEvent) -> None:
        """Deliver one event."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook with a no-op default
        """Flush and release resources; the default does nothing."""


class NoOpSkillObservabilitySink(SkillObservabilitySink):
    """Default sink that performs no I/O."""

    async def emit(self, event: SkillObservabilityEvent) -> None:
        """Discard the event."""
        del event


__all__ = [
    "NoOpSkillObservabilitySink",
    "SkillObservabilityEvent",
    "SkillObservabilitySink",
    "SkillObservabilityValue",
]
