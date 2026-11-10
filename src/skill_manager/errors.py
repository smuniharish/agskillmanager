"""Skill Manager exception hierarchy.

Every expected failure derives from `SkillManagerError`, so callers can catch
one base class or a precise subclass.
"""

from __future__ import annotations


class SkillManagerError(Exception):
    """Base class for expected Skill Manager failures."""


class OptionalDependencyError(SkillManagerError, ImportError):
    """An integration needs an extra that is not installed."""


class SkillValidationError(SkillManagerError):
    """A Skill document or domain value is invalid."""


class SkillNotFoundError(SkillManagerError):
    """No Skill matches the requested immutable ID or name and version."""


class SkillSourceError(SkillManagerError):
    """A Skill source failed to load, persist, or delete a Skill."""


class SkillDiscoveryError(SkillManagerError):
    """Discovery or ranking failed."""


class SkillDependencyError(SkillManagerError):
    """A dependency is missing or its version constraint cannot be satisfied."""


class SkillDependencyCycleError(SkillDependencyError):
    """The dependency graph contains a cycle.

    Attributes:
        path: Skill names along the cycle, starting and ending with the same name.
    """

    def __init__(self, path: tuple[str, ...]) -> None:
        self.path = path
        super().__init__("Skill dependency cycle: " + " -> ".join(path))


class SkillConflictError(SkillManagerError):
    """Two catalog entries conflict or an update is stale."""


class CapabilityResolutionError(SkillManagerError):
    """A required MCP capability could not be resolved."""


class SkillCreationDisabledError(SkillManagerError):
    """Agent Skill creation is disabled by policy."""


class SkillGenerationError(SkillManagerError):
    """A `SkillGenerator` could not produce a valid Skill."""


class SkillGovernanceError(SkillManagerError):
    """A governance policy does not permit the requested operation."""


class SkillApprovalError(SkillManagerError):
    """Approval could not be completed or persisted."""


class SkillRejectionError(SkillManagerError):
    """Rejection could not be completed or persisted."""


class SkillLifecycleError(SkillManagerError):
    """A Skill lifecycle transition is invalid."""


class SkillBundleError(SkillManagerError):
    """A SkillBundle could not be built."""
