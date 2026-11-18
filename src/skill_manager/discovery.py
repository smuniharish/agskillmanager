"""Bounded Skill discovery backed by the RetrievalLoom hybrid retrieval engine."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from retrievalloom import (
    And,
    DocumentInput,
    Eq,
    RetrievalEngine,
    Scope,
    SourceDescriptor,
    TextRepresentation,
)

from skill_manager.errors import SkillDiscoveryError
from skill_manager.models import Skill, SkillLifecycleState

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from retrievalloom import Components, EngineConfig, FilterExpression, IngestReport

_FILTER_KEYS = frozenset({"name", "version", "tag", "capability"})
_FILTER_FIELDS = {"name": "name", "version": "version", "tag": "tags", "capability": "capabilities"}
_FAILED_OUTCOMES = frozenset({"rejected", "failed"})
_INGEST_BATCH_SIZE = 1000
DEFAULT_SCOPE = Scope(tenant_id="agskillmanager", collection="skills")
"""The RetrievalLoom scope that `RetrievalLoomDiscoveryProvider` uses by default."""


class DiscoveryProvider(ABC):
    """Extension point for indexed, bounded Skill discovery.

    `SkillManager` keeps the provider's index in sync with the catalog and calls
    `discover` from `SkillManager.discover`.
    """

    @abstractmethod
    async def index(self, skills: Sequence[Skill]) -> None:
        """Replace the discoverable catalog snapshot."""

    @abstractmethod
    async def discover(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Skill]:
        """Return at most ``top_k`` active candidates."""

    async def aclose(self) -> None:  # noqa: B027
        """Release resources the provider owns; the default does nothing."""


def validate_filters(filters: Mapping[str, Any] | None) -> None:
    """Raise `SkillDiscoveryError` when ``filters`` uses an unsupported key.

    Supported keys are ``name``, ``version``, ``tag`` and ``capability``.
    """
    if filters:
        unknown = sorted(set(filters) - _FILTER_KEYS)
        if unknown:
            raise SkillDiscoveryError(f"unsupported Skill discovery filters: {unknown}")


def matches_filters(skill: Skill, filters: Mapping[str, Any] | None) -> bool:
    """Return whether ``skill`` is ``ACTIVE`` and satisfies every filter."""
    if skill.lifecycle.state is not SkillLifecycleState.ACTIVE:
        return False
    if not filters:
        return True
    checks = {
        "name": lambda expected: skill.metadata.name == expected,
        "version": lambda expected: skill.metadata.version == expected,
        "tag": lambda expected: expected in skill.metadata.tags,
        "capability": lambda expected: any(item.name == expected for item in skill.capabilities),
    }
    return all(checks[key](expected) for key, expected in filters.items())


def skill_document(skill: Skill) -> str:
    """Return the text that is indexed for ``skill``."""
    return "\n".join(
        (
            skill.metadata.name,
            skill.metadata.description,
            " ".join(skill.metadata.tags),
            "\n".join(skill.instructions),
            " ".join(capability.name for capability in skill.capabilities),
        )
    )


def _document(skill: Skill) -> DocumentInput:
    return DocumentInput(
        id=skill.skill_id,
        source=SourceDescriptor(uri=f"skill://{skill.skill_id}", title=skill.metadata.name),
        metadata={
            "name": skill.metadata.name,
            "version": skill.metadata.version,
            "tags": list(skill.metadata.tags),
            "capabilities": [capability.name for capability in skill.capabilities],
        },
        representations=[TextRepresentation(text=skill_document(skill))],
    )


def _filter_expression(filters: Mapping[str, Any] | None) -> FilterExpression | None:
    if not filters:
        return None
    clauses = [Eq(field=_FILTER_FIELDS[key], value=value) for key, value in filters.items()]
    return clauses[0] if len(clauses) == 1 else And(clauses=tuple(clauses))


def _check_report(report: IngestReport) -> None:
    failed = [item for item in report.documents if item.outcome.value in _FAILED_OUTCOMES]
    if failed:
        details = ", ".join(f"{item.document_id}: {item.outcome.value}" for item in failed)
        raise SkillDiscoveryError(f"RetrievalLoom did not index every Skill ({details})")


class RetrievalLoomDiscoveryProvider(DiscoveryProvider):
    """Discover Skills with a RetrievalLoom `RetrievalEngine`.

    Each active Skill is one RetrievalLoom document whose ID is the Skill ID and
    whose text is `skill_document`. Its name, version, tags and capability names
    are stored as metadata, so discovery filters run inside the engine. The
    default engine runs in memory with keyword, fuzzy and BM25 search; pass
    ``components`` (an embedding model, reranker, NLI model or durable stores) or
    a configured ``engine`` for semantic search, reranking and persistence.

    Every result is checked against the indexed catalog, so the provider never
    returns an inactive, filtered-out or unknown Skill. An empty query returns
    the active, filtered Skills ordered by Skill ID.

    Args:
        engine: A RetrievalLoom engine; the provider initializes it but leaves
            closing it to the caller. Mutually exclusive with ``config`` and
            ``components``.
        config: Configuration for an engine the provider creates and closes.
        components: Components for an engine the provider creates and closes.
        scope: The tenant and collection that hold the Skill documents.
        candidate_pool_size: Minimum number of results requested from the
            engine before the provider trims them to ``top_k``.

    Raises:
        ValueError: If ``engine`` is combined with ``config`` or ``components``,
            or ``candidate_pool_size`` is below 1.
    """

    def __init__(
        self,
        engine: RetrievalEngine | None = None,
        *,
        config: EngineConfig | None = None,
        components: Components | None = None,
        scope: Scope = DEFAULT_SCOPE,
        candidate_pool_size: int = 50,
    ) -> None:
        if engine is not None and (config is not None or components is not None):
            raise ValueError("pass either engine or config/components, not both")
        if candidate_pool_size < 1:
            raise ValueError("candidate_pool_size must be at least 1")
        self._owns_engine = engine is None
        self._engine = (
            engine if engine is not None else RetrievalEngine(config=config, components=components)
        )
        self._scope = scope
        self._candidate_pool_size = candidate_pool_size
        self._skills: dict[str, Skill] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    @property
    def engine(self) -> RetrievalEngine:
        """Return the underlying RetrievalLoom engine."""
        return self._engine

    @property
    def scope(self) -> Scope:
        """Return the RetrievalLoom scope that holds the Skill documents."""
        return self._scope

    async def _ready(self) -> None:
        if not self._initialized:
            try:
                await self._engine.initialize()
            except Exception as error:
                raise SkillDiscoveryError("RetrievalLoom engine failed to initialize") from error
            self._initialized = True

    async def index(self, skills: Sequence[Skill]) -> None:
        """Ingest new and changed active Skills and delete Skills no longer active."""
        active = {
            skill.skill_id: skill
            for skill in skills
            if skill.lifecycle.state is SkillLifecycleState.ACTIVE
        }
        async with self._lock:
            await self._ready()
            changed = [
                _document(skill)
                for skill_id, skill in active.items()
                if self._skills.get(skill_id) != skill
            ]
            removed = sorted(set(self._skills) - set(active))
            try:
                for start in range(0, len(changed), _INGEST_BATCH_SIZE):
                    batch = changed[start : start + _INGEST_BATCH_SIZE]
                    _check_report(await self._engine.ingest(batch, scope=self._scope))
                if removed:
                    await self._engine.delete(removed, scope=self._scope)
            except SkillDiscoveryError:
                raise
            except Exception as error:
                raise SkillDiscoveryError(
                    "RetrievalLoom could not index the Skill catalog"
                ) from error
            self._skills = active

    async def discover(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Skill]:
        """Return at most ``top_k`` active Skills in RetrievalLoom relevance order."""
        if top_k < 1:
            raise SkillDiscoveryError("top_k must be at least 1")
        validate_filters(filters)
        skills = self._skills
        if not query.strip():
            matches = sorted(
                (skill for skill in skills.values() if matches_filters(skill, filters)),
                key=lambda skill: skill.skill_id,
            )
            return matches[:top_k]
        await self._ready()
        try:
            result = await self._engine.retrieve(
                query,
                scope=self._scope,
                filters=_filter_expression(filters),
                top_k=max(top_k, self._candidate_pool_size),
            )
        except Exception as error:
            raise SkillDiscoveryError("RetrievalLoom Skill retrieval failed") from error
        ranked: dict[str, Skill] = {}
        for evidence in result.evidence:
            for source in evidence.sources:
                skill = skills.get(source.document_id)
                if skill is not None and matches_filters(skill, filters):
                    ranked.setdefault(skill.skill_id, skill)
        return list(ranked.values())[:top_k]

    async def aclose(self) -> None:
        """Close the engine if the provider created it."""
        if self._owns_engine:
            await self._engine.close()


__all__ = [
    "DEFAULT_SCOPE",
    "DiscoveryProvider",
    "RetrievalLoomDiscoveryProvider",
    "matches_filters",
    "skill_document",
    "validate_filters",
]
