from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

import skill_manager
from skill_manager import (
    OptionalDependencyError,
    Skill,
    SkillCapability,
    SkillDependency,
    SkillLifecycleState,
    SkillManagerConfig,
    SkillManagerError,
    SkillMetadata,
    SkillProvenance,
    SkillReference,
    is_skill_id,
)
from skill_manager import errors as errors_module
from tests.helpers import make_skill


def test_public_api_is_complete() -> None:
    assert all(hasattr(skill_manager, name) for name in skill_manager.__all__)
    assert skill_manager.__version__


def test_every_error_derives_from_the_base() -> None:
    for name in dir(errors_module):
        value = getattr(errors_module, name)
        if isinstance(value, type) and issubclass(value, Exception):
            assert issubclass(value, SkillManagerError)
    assert issubclass(OptionalDependencyError, ImportError)


def test_cycle_error_keeps_its_cycle() -> None:
    error = errors_module.SkillDependencyCycleError(("a", "b", "a"))
    assert error.path == ("a", "b", "a")
    assert "a -> b -> a" in str(error)


def test_config_defaults_and_bounds() -> None:
    config = SkillManagerConfig()
    assert config.allow_agent_skill_creation
    assert not config.require_human_approval
    with pytest.raises(ValidationError):
        SkillManagerConfig.model_validate({"max_document_bytes": 0})
    with pytest.raises(ValidationError):
        SkillManagerConfig(unknown=True)  # pyrefly: ignore[unexpected-keyword]


def test_skill_ids_are_generated_and_recognized() -> None:
    skill = make_skill()
    assert is_skill_id(skill.skill_id)
    assert not is_skill_id("sk_short")
    assert skill.skill_id != make_skill().skill_id


@pytest.mark.parametrize(
    "metadata",
    [
        {"name": "Bad Name", "version": "1.0.0", "description": "x"},
        {"name": "ok", "version": "not a version", "description": "x"},
        {"name": "ok", "version": "1.0.0", "description": "   "},
    ],
)
def test_metadata_is_validated(metadata: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SkillMetadata.model_validate(metadata)


def test_metadata_description_is_stripped() -> None:
    assert SkillMetadata(name="a", version="1", description=" x ").description == "x"


def test_dependency_validation() -> None:
    assert SkillDependency(name="base").version == "*"
    assert SkillDependency(name="base", version=">=1,<2").version == ">=1,<2"
    with pytest.raises(ValidationError):
        SkillDependency(name="Base")
    with pytest.raises(ValidationError):
        SkillDependency(name="base", version="nonsense")


def test_capability_validation() -> None:
    assert SkillCapability(name="github.pull_request:read").name
    with pytest.raises(ValidationError):
        SkillCapability(name="-bad name")


@pytest.mark.parametrize(
    "path", ["", "/abs", "~/home", "a\\b", "a/../b", "a//b", "./a", "c:/x", "a\x00"]
)
def test_reference_paths_must_be_safe(path: str) -> None:
    with pytest.raises(ValidationError):
        SkillReference(name="doc", path=path)


def test_reference_validation() -> None:
    assert SkillReference(name="doc", path="docs/readme.md").path == "docs/readme.md"
    with pytest.raises(ValidationError):
        SkillReference(name="Doc", path="a")


def test_provenance_validation() -> None:
    assert SkillProvenance(source=None).source is None
    assert SkillProvenance(source="https://example.com/skills").source
    with pytest.raises(ValidationError):
        SkillProvenance(created_at=datetime(2026, 1, 1))  # noqa: DTZ001
    with pytest.raises(ValidationError):
        SkillProvenance(source="https://user:pass@example.com")
    with pytest.raises(ValidationError):
        SkillProvenance(source="x" * 1025)
    with pytest.raises(ValidationError):
        SkillProvenance(generation_context={"api_key": "value"})
    with pytest.raises(ValidationError):
        SkillProvenance(parent_skill_ids=("nope",))


@pytest.mark.parametrize(
    "update",
    [
        {"skill_id": "bad"},
        {"api_version": "2.0"},
        {"kind": "agent"},
        {"instructions": ()},
        {"instructions": ("  ",)},
        {"instructions": ("x" * 12001,)},
        {"dependencies": [{"name": "a"}, {"name": "a"}]},
        {"capabilities": [{"name": "a"}, {"name": "a"}]},
        {"prompts": {"password": "x"}},
    ],
)
def test_skill_rejects_invalid_documents(update: dict[str, object]) -> None:
    document = make_skill().model_dump(mode="json") | update
    with pytest.raises(ValidationError):
        Skill.model_validate(document)


def test_skill_rejects_duplicate_parents() -> None:
    parent = make_skill().skill_id
    document = make_skill().model_dump(mode="json")
    document["provenance"]["parent_skill_ids"] = [parent, parent]
    with pytest.raises(ValidationError):
        Skill.model_validate(document)


def test_skill_instructions_are_stripped_and_state_defaults_active() -> None:
    skill = make_skill(instructions=("  Do it.  ",))
    assert skill.instructions == ("Do it.",)
    assert skill.lifecycle.state is SkillLifecycleState.ACTIVE
