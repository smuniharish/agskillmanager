"""Immutable, validated Skill domain models."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlsplit

from mcp_capability_router import Capability
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ID_PATTERN = re.compile(r"^sk_[0-9A-HJKMNP-TV-Z]{26}$")
_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")
_SECRET_KEY_PATTERN = re.compile(
    r"(?:secret|password|token|credential|api[_-]?key|authorization)", re.I
)


def is_skill_id(value: str) -> bool:
    """Return whether ``value`` is a well-formed immutable Skill ID."""
    return _ID_PATTERN.fullmatch(value) is not None


def _new_skill_id() -> str:
    value = secrets.randbits(128)
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _ID_ALPHABET[value & 31]
        value >>= 5
    return "sk_" + "".join(chars)


class FrozenModel(BaseModel):
    """Base for frozen, extra-forbid public domain models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SkillLifecycleState(StrEnum):
    """Supported Skill lifecycle states."""

    ACTIVE = "ACTIVE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"


class SkillOrigin(StrEnum):
    """Origin category for a Skill revision."""

    HUMAN = "human"
    AGENT = "agent"
    IMPORTED = "imported"
    SYSTEM = "system"


class SkillMetadata(FrozenModel):
    """Human-readable identity and semantic version metadata."""

    name: str
    version: str
    description: str
    tags: tuple[str, ...] = ()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a lowercase hyphenated name of at most 63 characters."""
        if not _NAME_PATTERN.fullmatch(value):
            raise ValueError("name must be lowercase alphanumeric words separated by hyphens")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Require a PEP 440 version."""
        try:
            Version(value)
        except InvalidVersion as error:
            raise ValueError("version must be a valid PEP 440 version") from error
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """Require 1 to 4000 characters and strip surrounding whitespace."""
        if not value.strip() or len(value) > 4000:
            raise ValueError("description must contain 1 to 4000 characters")
        return value.strip()


class SkillDependency(FrozenModel):
    """A named Skill requirement with a PEP 440 version constraint."""

    name: str
    version: str = "*"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a valid Skill name."""
        if not _NAME_PATTERN.fullmatch(value):
            raise ValueError("dependency name is invalid")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Require ``*`` or a PEP 440 specifier set."""
        if value != "*":
            SpecifierSet(value)
        return value


class SkillCapability(FrozenModel):
    """A required MCP capability expressed by its canonical name."""

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require 1 to 200 safe capability-name characters."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", value):
            raise ValueError("capability name must contain 1 to 200 safe characters")
        return value


class SkillReference(FrozenModel):
    """A safe, source-relative resource reference."""

    name: str
    path: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a valid resource name."""
        if not _NAME_PATTERN.fullmatch(value):
            raise ValueError("resource name is invalid")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Require a relative POSIX path without traversal, drive or scheme."""
        if not value or "\\" in value or "\x00" in value or value.startswith(("/", "~")):
            raise ValueError("resource path must be a safe relative POSIX path")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("resource path may not contain empty, '.' or '..' segments")
        if ":" in parts[0]:
            raise ValueError("resource path may not include a drive or URI scheme")
        return value


class SkillProvenance(FrozenModel):
    """Origin and lineage facts for this immutable Skill revision."""

    origin: SkillOrigin = SkillOrigin.HUMAN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str | None = None
    generation_context: dict[str, str] = Field(default_factory=dict)
    parent_skill_ids: tuple[str, ...] = ()

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require a timezone-aware timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("source")
    @classmethod
    def reject_credential_urls(cls, value: str | None) -> str | None:
        """Reject over-long sources and URLs with embedded credentials."""
        if value is None:
            return value
        if len(value) > 1024:
            raise ValueError("provenance source is too long")
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("provenance source may not contain URL credentials")
        return value

    @field_validator("generation_context")
    @classmethod
    def reject_secret_keys(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject context keys that name credentials or secrets."""
        if any(_SECRET_KEY_PATTERN.search(key) for key in value):
            raise ValueError("generation_context may not serialize credentials or secrets")
        return value

    @field_validator("parent_skill_ids")
    @classmethod
    def validate_parent_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require every parent to be a well-formed Skill ID."""
        if any(not _ID_PATTERN.fullmatch(item) for item in value):
            raise ValueError("parent Skill IDs must use the immutable Skill ID format")
        return value


class SkillLifecycle(FrozenModel):
    """Current lifecycle state and transition timestamp."""

    state: SkillLifecycleState = SkillLifecycleState.ACTIVE
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = None


class SkillGovernance(FrozenModel):
    """Approval and rejection audit references owned by the Skill domain."""

    approval_event_id: str | None = None
    rejection_event_id: str | None = None
    reviewer: str | None = None
    reason: str | None = None


class Skill(FrozenModel):
    """Canonical, immutable Skill revision."""

    api_version: str = "1.0"
    kind: str = "skill"
    skill_id: str = Field(default_factory=_new_skill_id)
    revision: Annotated[int, Field(ge=1)] = 1
    metadata: SkillMetadata
    instructions: tuple[str, ...]
    dependencies: tuple[SkillDependency, ...] = ()
    capabilities: tuple[SkillCapability, ...] = ()
    resources: tuple[SkillReference, ...] = ()
    prompts: dict[str, str] = Field(default_factory=dict)
    provenance: SkillProvenance = Field(default_factory=SkillProvenance)
    lifecycle: SkillLifecycle = Field(default_factory=SkillLifecycle)
    governance: SkillGovernance = Field(default_factory=SkillGovernance)

    @field_validator("skill_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Require the ``sk_`` plus 26-character ULID format."""
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("skill_id must use the immutable 'sk_' plus 26-character ULID format")
        return value

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        """Require schema version ``1.0``."""
        if value != "1.0":
            raise ValueError(f"unsupported Skill schema version: {value!r}")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        """Require kind ``skill``."""
        if value != "skill":
            raise ValueError("kind must be 'skill'")
        return value

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Enforce instruction count and size limits and strip whitespace."""
        if (
            not value
            or len(value) > 100
            or any(not item.strip() or len(item) > 12000 for item in value)
            or sum(len(item) for item in value) > 100_000
        ):
            raise ValueError("instructions exceed schema count or size limits")
        return tuple(item.strip() for item in value)

    @model_validator(mode="after")
    def validate_unique_declarations(self) -> Skill:
        """Reject duplicate declarations and secret-like prompt keys."""
        dep_names = [dependency.name for dependency in self.dependencies]
        if len(dep_names) != len(set(dep_names)):
            raise ValueError("duplicate dependency names are not allowed")
        cap_names = [capability.name for capability in self.capabilities]
        if len(cap_names) != len(set(cap_names)):
            raise ValueError("duplicate required capabilities are not allowed")
        if len(self.provenance.parent_skill_ids) != len(set(self.provenance.parent_skill_ids)):
            raise ValueError("duplicate parent Skill IDs are not allowed")
        if any(_SECRET_KEY_PATTERN.search(key) for key in self.prompts):
            raise ValueError("prompt keys may not represent serialized credentials or secrets")
        return self


class SkillBundle(FrozenModel):
    """Resolved Skill data for an application; this value is not a runtime."""

    skills: tuple[Skill, ...]
    instructions: tuple[str, ...]
    dependency_order: tuple[str, ...]
    dependencies: tuple[SkillDependency, ...]
    capabilities: dict[str, tuple[Capability, ...]] = Field(default_factory=dict)
    resources: tuple[SkillReference, ...] = ()
    prompts: dict[str, str] = Field(default_factory=dict)
    provenance: tuple[SkillProvenance, ...]
    metadata: dict[str, str] = Field(default_factory=dict)
