from __future__ import annotations

import builtins
from datetime import UTC, datetime
from typing import Any

import pytest

from skill_manager import (
    DefaultSkillValidator,
    NoOpSkillObservabilitySink,
    OptionalDependencyError,
    SkillGenerationRequest,
    SkillLifecycleState,
    SkillObservabilityEvent,
    SkillValidationError,
    dump_skill_yaml,
    parse_skill_yaml,
)
from skill_manager._optional import optional_import
from tests.helpers import StaticGenerator, make_skill


async def test_yaml_round_trip() -> None:
    skill = make_skill(tags=("ops",), prompts={"system": "Be brief."})
    assert await parse_skill_yaml(dump_skill_yaml(skill)) == skill


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("key: [unclosed", "malformed"),
        ("- a list", "must be a mapping"),
        ("kind: skill", "skill_id is required"),
    ],
)
async def test_invalid_yaml_is_rejected(content: str, message: str) -> None:
    with pytest.raises(SkillValidationError, match=message):
        await parse_skill_yaml(content)


async def test_schema_mismatch_and_size_limit() -> None:
    with pytest.raises(SkillValidationError, match="schema"):
        await parse_skill_yaml("skill_id: sk_00000000000000000000000000")
    with pytest.raises(SkillValidationError, match="byte document limit"):
        await parse_skill_yaml(dump_skill_yaml(make_skill()), max_bytes=10)


async def test_yaml_never_executes_tags() -> None:
    with pytest.raises(SkillValidationError):
        await parse_skill_yaml("!!python/object/apply:os.system ['echo']")


async def test_default_validator_rejects_active_rejected_revision() -> None:
    validator = DefaultSkillValidator()
    skill = make_skill()
    assert await validator.validate(skill) is skill
    rejected = skill.model_copy(
        update={"governance": skill.governance.model_copy(update={"rejection_event_id": "e"})}
    )
    with pytest.raises(SkillValidationError):
        await validator.validate(rejected)
    pending = make_skill(state=SkillLifecycleState.REJECTED).model_copy(
        update={"governance": rejected.governance}
    )
    assert await validator.validate(pending) is pending


async def test_noop_sink_accepts_and_closes() -> None:
    sink = NoOpSkillObservabilitySink()
    event = SkillObservabilityEvent("skill.registered", attributes={"a": 1})
    await sink.emit(event)
    await sink.aclose()
    assert event.occurred_at.tzinfo is UTC


async def test_generator_name_defaults_to_class_name() -> None:
    generator = StaticGenerator(make_skill())
    request = SkillGenerationRequest(input="task")
    assert generator.name == "StaticGenerator"
    assert await generator.generate(request) is generator.skill
    assert request.parent is None
    assert request.feedback == ()


def test_optional_import_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    assert optional_import("json", "core").dumps({}) == "{}"
    real_import = builtins.__import__

    def blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "missing_module_for_test":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(OptionalDependencyError, match=r"skill-manager\[extra\]"):
        optional_import("missing_module_for_test", "extra")


def test_event_timestamps_are_aware() -> None:
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    assert SkillObservabilityEvent("x", occurred_at=moment).occurred_at == moment
