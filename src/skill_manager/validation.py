"""Safe YAML parsing and Skill domain validation."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import yaml
from pydantic import ValidationError

from skill_manager.errors import SkillValidationError
from skill_manager.models import Skill, SkillLifecycleState


class SkillValidator(ABC):
    """Extension point for application-specific Skill validation.

    `SkillManager` validates every Skill it registers or loads. Subclass
    `DefaultSkillValidator` and call ``super().validate`` to keep the built-in
    invariants while adding your own.

    Example:
        ```python
        class RequireTags(DefaultSkillValidator):
            async def validate(self, skill):
                skill = await super().validate(skill)
                if not skill.metadata.tags:
                    raise SkillValidationError("every Skill needs at least one tag")
                return skill
        ```
    """

    @abstractmethod
    async def validate(self, skill: Skill) -> Skill:
        """Validate and return a normalized Skill.

        Raises:
            SkillValidationError: If the Skill violates a rule.
        """


class DefaultSkillValidator(SkillValidator):
    """Enforce lifecycle and governance invariants beyond the model schema."""

    async def validate(self, skill: Skill) -> Skill:
        """Reject an ``ACTIVE`` Skill that carries a rejection event."""
        if (
            skill.lifecycle.state is SkillLifecycleState.ACTIVE
            and skill.governance.rejection_event_id
        ):
            raise SkillValidationError("a rejected Skill revision cannot be active")
        return skill


def _load_mapping(content: str) -> dict[str, Any]:
    try:
        value: Any = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise SkillValidationError("malformed Skill YAML") from error
    if not isinstance(value, dict):
        raise SkillValidationError("a Skill YAML document must be a mapping")
    return value


async def parse_skill_yaml(content: str, *, max_bytes: int = 1_000_000) -> Skill:
    """Parse one Skill YAML document without executing any of it.

    Parsing runs in a worker thread so large documents never block the event loop.

    Args:
        content: The YAML text.
        max_bytes: Largest accepted UTF-8 size.

    Returns:
        The schema-valid Skill; run a `SkillValidator` afterwards for policy checks.

    Raises:
        SkillValidationError: If the document is too large, malformed, lacks an
            explicit ``skill_id``, or does not match the Skill schema.
    """
    if len(content.encode()) > max_bytes:
        raise SkillValidationError(f"Skill YAML exceeds the {max_bytes}-byte document limit")
    value = await asyncio.to_thread(_load_mapping, content)
    if "skill_id" not in value:
        raise SkillValidationError("skill_id is required in persisted Skill YAML")
    try:
        return Skill.model_validate(value)
    except ValidationError as error:
        raise SkillValidationError("Skill YAML does not match Skill schema version 1.0") from error


def dump_skill_yaml(skill: Skill) -> str:
    """Serialize a Skill to the canonical YAML document format."""
    return yaml.safe_dump(skill.model_dump(mode="json"), allow_unicode=True, sort_keys=True)
