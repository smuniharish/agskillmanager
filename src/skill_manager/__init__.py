"""Framework-agnostic Skill lifecycle management for AI agents.

`SkillManager` validates, stores, discovers, governs and composes Skills; it
never runs an agent. Every extension point is an abstract base class, and every
collaborator is injected fully built.
"""

from importlib.metadata import version

from skill_manager.api import SkillManager
from skill_manager.config import SkillManagerConfig
from skill_manager.discovery import (
    DiscoveryProvider,
    LexicalSkillRetriever,
    PipelineDiscoveryProvider,
    RetrievedSkill,
    ScoreSkillReranker,
    SemanticSkillRetriever,
    SkillReranker,
    SkillRetriever,
    matches_filters,
    skill_document,
    validate_filters,
)
from skill_manager.errors import (
    CapabilityResolutionError,
    OptionalDependencyError,
    SkillApprovalError,
    SkillBundleError,
    SkillConflictError,
    SkillCreationDisabledError,
    SkillDependencyCycleError,
    SkillDependencyError,
    SkillDiscoveryError,
    SkillGenerationError,
    SkillGovernanceError,
    SkillLifecycleError,
    SkillManagerError,
    SkillNotFoundError,
    SkillRejectionError,
    SkillSourceError,
    SkillValidationError,
)
from skill_manager.generation import SkillFeedback, SkillGenerationRequest, SkillGenerator
from skill_manager.models import (
    Skill,
    SkillBundle,
    SkillCapability,
    SkillDependency,
    SkillGovernance,
    SkillLifecycle,
    SkillLifecycleState,
    SkillMetadata,
    SkillOrigin,
    SkillProvenance,
    SkillReference,
    is_skill_id,
)
from skill_manager.observability import (
    NoOpSkillObservabilitySink,
    SkillObservabilityEvent,
    SkillObservabilitySink,
    SkillObservabilityValue,
)
from skill_manager.registry import InMemorySkillRegistry, SkillRegistry
from skill_manager.resolution import resolve_dependencies
from skill_manager.sources import FilesystemSkillSource, SkillSource
from skill_manager.validation import (
    DefaultSkillValidator,
    SkillValidator,
    dump_skill_yaml,
    parse_skill_yaml,
)

__version__ = version("skill-manager")

__all__ = [
    "CapabilityResolutionError",
    "DefaultSkillValidator",
    "DiscoveryProvider",
    "FilesystemSkillSource",
    "InMemorySkillRegistry",
    "LexicalSkillRetriever",
    "NoOpSkillObservabilitySink",
    "OptionalDependencyError",
    "PipelineDiscoveryProvider",
    "RetrievedSkill",
    "ScoreSkillReranker",
    "SemanticSkillRetriever",
    "Skill",
    "SkillApprovalError",
    "SkillBundle",
    "SkillBundleError",
    "SkillCapability",
    "SkillConflictError",
    "SkillCreationDisabledError",
    "SkillDependency",
    "SkillDependencyCycleError",
    "SkillDependencyError",
    "SkillDiscoveryError",
    "SkillFeedback",
    "SkillGenerationError",
    "SkillGenerationRequest",
    "SkillGenerator",
    "SkillGovernance",
    "SkillGovernanceError",
    "SkillLifecycle",
    "SkillLifecycleError",
    "SkillLifecycleState",
    "SkillManager",
    "SkillManagerConfig",
    "SkillManagerError",
    "SkillMetadata",
    "SkillNotFoundError",
    "SkillObservabilityEvent",
    "SkillObservabilitySink",
    "SkillObservabilityValue",
    "SkillOrigin",
    "SkillProvenance",
    "SkillReference",
    "SkillRegistry",
    "SkillRejectionError",
    "SkillReranker",
    "SkillRetriever",
    "SkillSource",
    "SkillSourceError",
    "SkillValidationError",
    "SkillValidator",
    "__version__",
    "dump_skill_yaml",
    "is_skill_id",
    "matches_filters",
    "parse_skill_yaml",
    "resolve_dependencies",
    "skill_document",
    "validate_filters",
]
