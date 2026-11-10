"""Framework-agnostic contract for agent Skill generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from skill_manager.models import Skill


@dataclass(frozen=True, slots=True)
class SkillFeedback:
    """One rejection recorded against a parent Skill revision.

    Attributes:
        feedback_id: The feedback-manager event ID.
        payload: The rejection payload, including the reviewer's ``feedback`` text.
        metadata: Reviewer-supplied metadata.
        created_at: When the rejection was submitted.
    """

    feedback_id: str
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SkillGenerationRequest:
    """Everything a `SkillGenerator` receives for one generation.

    Attributes:
        input: The caller's task description, prompt or structured input.
        parent: The rejected revision being improved, if any.
        feedback: Rejections of ``parent``, newest first.
    """

    input: Any
    parent: Skill | None = None
    feedback: tuple[SkillFeedback, ...] = field(default=())


class SkillGenerator(ABC):
    """Extension point that turns a request into a candidate Skill.

    Implement it with any model, agent framework or rule engine.
    `SkillManager.generate_skill` stamps agent provenance, lineage and the
    lifecycle state on the result, then validates and registers it, so a
    generator only needs to produce the Skill content. With the ``langchain``
    extra, `skill_manager.integrations.langchain.XStructuredSkillGenerator`
    wraps any LangChain chat model.

    Example:
        ```python
        class TemplateGenerator(SkillGenerator):
            async def generate(self, request):
                return Skill(
                    metadata=SkillMetadata(name="echo", version="1.0.0", description="Echo."),
                    instructions=(f"Repeat: {request.input}",),
                )
        ```
    """

    @property
    def name(self) -> str:
        """Return the provenance source recorded on generated Skills."""
        return type(self).__name__

    @abstractmethod
    async def generate(self, request: SkillGenerationRequest) -> Skill:
        """Return one candidate Skill.

        Raises:
            SkillGenerationError: If no valid Skill can be produced.
        """


__all__ = ["SkillFeedback", "SkillGenerationRequest", "SkillGenerator"]
