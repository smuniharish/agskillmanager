"""Async application facade for Skill lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import re
import weakref
from collections import OrderedDict, deque
from collections.abc import AsyncGenerator, Hashable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from types import MappingProxyType, TracebackType
from typing import TYPE_CHECKING, Any, Self
from uuid import UUID

from agxai import DecisionType, EvidenceType, XAIRuntime
from feedback_manager import (
    FeedbackCategory,
    FeedbackEvent,
    FeedbackManager,
    FeedbackManagerError,
    FeedbackQuery,
    FeedbackSource,
    FeedbackStatus,
    FeedbackTarget,
    FeedbackTargetType,
)
from mcp_capability_router import Capability, MCPCapabilityRouterError, MCPRuntime
from pydantic import ValidationError
from refresh_engine import (
    AsyncScheduler,
    EventPublisher,
    RefreshEngine,
    RefreshError,
    RefreshMode,
    RefreshResult,
    RefreshStatus,
    ResourceSelector,
    TriggerSource,
)

from skill_manager._xai import record_decision
from skill_manager.config import SkillManagerConfig
from skill_manager.discovery import DiscoveryProvider, PipelineDiscoveryProvider
from skill_manager.errors import (
    CapabilityResolutionError,
    SkillApprovalError,
    SkillBundleError,
    SkillConflictError,
    SkillCreationDisabledError,
    SkillGovernanceError,
    SkillLifecycleError,
    SkillManagerError,
    SkillNotFoundError,
    SkillRejectionError,
    SkillSourceError,
)
from skill_manager.generation import SkillFeedback, SkillGenerationRequest, SkillGenerator
from skill_manager.models import (
    Skill,
    SkillBundle,
    SkillGovernance,
    SkillLifecycle,
    SkillLifecycleState,
    SkillOrigin,
)
from skill_manager.observability import (
    NoOpSkillObservabilitySink,
    SkillObservabilityEvent,
    SkillObservabilitySink,
    SkillObservabilityValue,
)
from skill_manager.registry import InMemorySkillRegistry, SkillRegistry
from skill_manager.resolution import resolve_dependencies
from skill_manager.validation import DefaultSkillValidator, SkillValidator, parse_skill_yaml

if TYPE_CHECKING:
    from skill_manager.sources import SkillSource

logger = logging.getLogger(__name__)
_SECRET_KEY = re.compile(r"(?:secret|password|token|credential|api[_-]?key|authorization)", re.I)
_SKILL_TARGET = FeedbackTargetType("skill")


def _reject_secret_keys(metadata: Mapping[str, Any]) -> None:
    for key, value in metadata.items():
        if _SECRET_KEY.search(key):
            raise SkillGovernanceError("feedback metadata may not contain credential-like keys")
        if isinstance(value, Mapping):
            _reject_secret_keys(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                if isinstance(item, Mapping):
                    _reject_secret_keys(item)


class _KeyedLocks:
    """One asyncio lock per key, dropped as soon as nobody holds or awaits it."""

    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[Hashable, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def __call__(self, key: Hashable) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock


class SkillManager:
    """Manage the Skill lifecycle and hand resolved Skills to any agent framework.

    The manager validates, stores, discovers, governs and composes Skills. It
    never executes a Skill or runs an agent, so it works with LangGraph, CrewAI,
    Agno or plain Python alike. Every collaborator is an injected, fully built
    instance, so each downstream package keeps all of its own options.

    Use it as an async context manager, or call `aclose` when done:

    ```python
    async with SkillManager(sources=[FilesystemSkillSource("skills")]) as manager:
        skill = await manager.load("summarize-ticket")
    ```

    Args:
        sources: Skill sources; the first is the default write target.
        registry: Catalog; defaults to `InMemorySkillRegistry`.
        discovery: Discovery provider; defaults to lexical `PipelineDiscoveryProvider`.
        validator: Policy validator; defaults to `DefaultSkillValidator`.
        config: Policy switches and limits.
        feedback_manager: Records approvals and rejections; defaults to an
            in-memory `FeedbackManager` that the manager owns and closes.
        mcp_runtime: Resolves required MCP capabilities in `build_bundle`.
        refresh_engine: Refreshed before sources are reloaded in `refresh`.
        xai_runtime: Receives evidence and decisions for generation,
            approval, rejection and bundle composition.
        observability_sink: Receives sanitized lifecycle events.

    Raises:
        ValueError: If two sources share a ``source_id``.
    """

    def __init__(
        self,
        *,
        sources: Iterable[SkillSource] = (),
        registry: SkillRegistry | None = None,
        discovery: DiscoveryProvider | None = None,
        validator: SkillValidator | None = None,
        config: SkillManagerConfig | None = None,
        feedback_manager: FeedbackManager | None = None,
        mcp_runtime: MCPRuntime | None = None,
        refresh_engine: RefreshEngine | None = None,
        xai_runtime: XAIRuntime | None = None,
        observability_sink: SkillObservabilitySink | None = None,
    ) -> None:
        self.config = config if config is not None else SkillManagerConfig()
        self._sources = tuple(sources)
        self._source_by_id = {source.source_id: source for source in self._sources}
        if len(self._source_by_id) != len(self._sources):
            raise ValueError("Skill source IDs must be unique")
        self._registry = registry if registry is not None else InMemorySkillRegistry()
        self._discovery = discovery if discovery is not None else PipelineDiscoveryProvider()
        self._validator = validator if validator is not None else DefaultSkillValidator()
        self._owns_feedback = feedback_manager is None
        self._feedback = feedback_manager if feedback_manager is not None else FeedbackManager()
        self._mcp_runtime = mcp_runtime
        self._refresh_engine = refresh_engine
        self._xai = xai_runtime
        self._observability = (
            observability_sink if observability_sink is not None else NoOpSkillObservabilitySink()
        )
        self._observability_errors: deque[Exception] = deque(maxlen=self.config.error_history_size)
        self._source_errors: dict[str, str] = {}
        self._source_for_skill: dict[str, str] = {}
        self._documents_by_source: dict[str, dict[str, str]] = {}
        self._source_locks = {source.source_id: asyncio.Lock() for source in self._sources}
        self._catalog_locks = _KeyedLocks()
        self._lifecycle_locks = _KeyedLocks()
        self._load_lock = asyncio.Lock()
        self._reindex_lock = asyncio.Lock()
        self._scheduler_lock = asyncio.Lock()
        self._capabilities: OrderedDict[str, Capability] = OrderedDict()
        self._capability_epoch = 0
        self._catalog_version = 0
        self._index_dirty = True
        self._loaded = False
        self._scheduler: AsyncScheduler | None = None

    async def __aenter__(self) -> Self:
        """Return the manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the manager."""
        await self.aclose()

    @property
    def source_errors(self) -> Mapping[str, str]:
        """Return the latest per-source and per-document load errors."""
        return MappingProxyType(dict(self._source_errors))

    @property
    def observability_errors(self) -> tuple[Exception, ...]:
        """Return recent sink and XAI failures that did not interrupt Skill operations."""
        return tuple(self._observability_errors)

    async def load(self, name_or_skill_id: str, *, version: str | None = None) -> Skill:
        """Return a Skill by immutable ID, or the active Skill with a name and optional version.

        Raises:
            SkillNotFoundError: If no Skill matches.
            SkillSourceError: If nothing matches and a source failed to load,
                so the Skill may exist in the unreadable source.
        """
        await self._ensure_loaded()
        try:
            if name_or_skill_id.startswith("sk_"):
                return await self._registry.get(name_or_skill_id)
            return await self._registry.by_name(name_or_skill_id, version)
        except SkillNotFoundError:
            if self._source_errors:
                raise SkillSourceError(
                    "Skill sources could not all be read; see manager.source_errors"
                ) from None
            raise

    async def discover(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Skill]:
        """Return at most ``top_k`` active Skills ranked for ``query``.

        Args:
            query: Natural-language task description.
            top_k: Maximum number of Skills.
            filters: Exact ``name``, ``version``, ``tag`` or ``capability`` filters.
        """
        await self._ensure_loaded()
        await self._reindex_if_needed()
        matches = await self._discovery.discover(query, top_k=top_k, filters=filters)
        await self._emit(
            "skill.discovery.completed",
            query_length=len(query),
            requested_top_k=top_k,
            result_count=len(matches),
            filtered=bool(filters),
        )
        return matches

    async def register_skill(self, skill: Skill, *, source_id: str | None = None) -> Skill:
        """Validate, govern, register and persist one Skill revision.

        Agent Skills are held in ``PENDING_APPROVAL`` when human approval is
        required; pending revisions stay in the registry until they are approved.

        Args:
            skill: The revision to register.
            source_id: Source to persist to; defaults to the first source.

        Returns:
            The registered Skill, with its governed lifecycle state.

        Raises:
            SkillCreationDisabledError: If agent Skills are disabled.
            SkillGovernanceError: If an agent Skill bypasses policy.
            SkillValidationError: If the validator rejects the Skill.
            SkillConflictError: If the revision conflicts with the catalog.
            SkillSourceError: If persistence fails.
        """
        await self._ensure_loaded()
        if skill.provenance.origin is SkillOrigin.AGENT:
            self._require_agent_creation()
            if self.config.require_human_approval:
                skill = skill.model_copy(
                    update={"lifecycle": SkillLifecycle(state=SkillLifecycleState.PENDING_APPROVAL)}
                )
            elif skill.lifecycle.state is not SkillLifecycleState.ACTIVE:
                raise SkillGovernanceError(
                    "agent Skill must be ACTIVE when human approval is disabled"
                )
        skill = await self._validator.validate(skill)
        source = self._select_source(source_id)
        await self._write(
            skill, source, persist=skill.lifecycle.state is not SkillLifecycleState.PENDING_APPROVAL
        )
        logger.info(
            "skill_registered",
            extra={"skill_id": skill.skill_id, "state": skill.lifecycle.state.value},
        )
        await self._emit(
            "skill.registered",
            skill_id=skill.skill_id,
            skill_name=skill.metadata.name,
            skill_version=skill.metadata.version,
            lifecycle_state=skill.lifecycle.state.value,
            origin=skill.provenance.origin.value,
            persisted=source is not None,
        )
        return skill

    async def generate_skill(
        self,
        generator: SkillGenerator,
        input: Any,
        *,
        parent_skill_id: str | None = None,
        source_id: str | None = None,
    ) -> Skill:
        """Generate, govern and register an agent Skill.

        With ``parent_skill_id``, the generator also receives the parent revision
        and its recorded rejections, and the result becomes the next revision
        in the parent's lineage.

        Args:
            generator: Produces the candidate Skill.
            input: Task description passed to the generator.
            parent_skill_id: Rejected revision to improve.
            source_id: Source to persist to; defaults to the first source.

        Raises:
            SkillCreationDisabledError: If agent Skills are disabled.
            SkillGenerationError: If the generator cannot produce a Skill.
        """
        self._require_agent_creation()
        parent = await self.load(parent_skill_id) if parent_skill_id is not None else None
        feedback = await self._rejections(parent) if parent is not None else ()
        candidate = await generator.generate(
            SkillGenerationRequest(input=input, parent=parent, feedback=feedback)
        )
        lineage = (parent.skill_id,) if parent is not None else ()
        candidate = candidate.model_copy(
            update={
                "provenance": candidate.provenance.model_copy(
                    update={
                        "origin": SkillOrigin.AGENT,
                        "source": generator.name,
                        "created_at": datetime.now(UTC),
                        "parent_skill_ids": lineage,
                    }
                ),
                "revision": parent.revision + 1 if parent is not None else 1,
                "lifecycle": SkillLifecycle(),
                "governance": SkillGovernance(),
            }
        )
        skill = await self.register_skill(candidate, source_id=source_id)
        await self._explain(
            "generate_skill",
            decision_type=DecisionType.CUSTOM,
            evidence_type=EvidenceType.MODEL_OUTPUT,
            summary=(
                f"{generator.name} generated Skill {skill.metadata.name} {skill.metadata.version}"
            ),
            skill=skill,
            parent_skill_id=parent_skill_id or "",
            feedback_count=len(feedback),
        )
        return skill

    async def approve_skill(
        self,
        skill_id: str,
        *,
        reviewer: str | None = None,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Skill:
        """Record a human approval and activate a ``PENDING_APPROVAL`` Skill.

        The approval is submitted to feedback-manager, the active revision is
        persisted, and only then is the feedback event resolved. If resolving
        fails, the Skill is returned to ``PENDING_APPROVAL``.

        Raises:
            SkillLifecycleError: If the Skill is not pending.
            SkillGovernanceError: If ``metadata`` contains credential-like keys.
            SkillApprovalError: If feedback or persistence fails.
        """
        return await self._decide(
            skill_id, approve=True, reviewer=reviewer, reason=reason, metadata=metadata
        )

    async def reject_skill(
        self,
        skill_id: str,
        *,
        feedback: str,
        reviewer: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Skill:
        """Record a human rejection and retain the ``REJECTED`` revision for audit.

        The ``feedback`` text is later passed to a `SkillGenerator` through
        `generate_skill` with ``parent_skill_id``.

        Raises:
            SkillLifecycleError: If the Skill is not pending.
            SkillRejectionError: If ``feedback`` is empty, or feedback or persistence fails.
        """
        if not feedback.strip():
            raise SkillRejectionError("rejection feedback must not be empty")
        return await self._decide(
            skill_id, approve=False, reviewer=reviewer, reason=feedback, metadata=metadata
        )

    async def list_skills(
        self,
        *,
        states: Iterable[SkillLifecycleState] | None = None,
        origins: Iterable[SkillOrigin] | None = None,
    ) -> tuple[Skill, ...]:
        """Return registered revisions, optionally filtered by lifecycle state and origin."""
        await self._ensure_loaded()
        skills = await self._registry.all(states=states)
        if origins is None:
            return skills
        wanted = frozenset(origins)
        return tuple(skill for skill in skills if skill.provenance.origin in wanted)

    async def list_pending_skills(self) -> tuple[Skill, ...]:
        """Return the review queue: every ``PENDING_APPROVAL`` revision."""
        return await self.list_skills(states={SkillLifecycleState.PENDING_APPROVAL})

    async def remove_skill(self, skill_id: str) -> None:
        """Delete a non-rejected revision from its source and the catalog.

        Raises:
            SkillLifecycleError: If the Skill is ``REJECTED``; rejections are kept for audit.
        """
        await self._ensure_loaded()
        skill = await self._registry.get(skill_id)
        if skill.lifecycle.state is SkillLifecycleState.REJECTED:
            raise SkillLifecycleError("rejected revisions are retained for auditability")
        source = self._source_by_id.get(self._source_for_skill.get(skill_id, ""))
        async with self._locked(skill, source):
            if source is not None:
                await source.delete(skill_id)
            await self._registry.remove(skill_id)
            self._source_for_skill.pop(skill_id, None)
            self._mark_index_dirty()
        await self._emit("skill.removed", skill_id=skill_id, skill_name=skill.metadata.name)

    async def build_bundle(self, skills: Iterable[Skill | str]) -> SkillBundle:
        """Resolve dependencies and MCP capabilities into a `SkillBundle`.

        Args:
            skills: Root Skills, or their IDs or names.

        Raises:
            SkillBundleError: If no root is given, a root is not ``ACTIVE``, or
                two Skills define the same prompt key differently.
            SkillDependencyError: If a dependency cannot be resolved.
            CapabilityResolutionError: If a required capability is unavailable.
        """
        roots: list[Skill] = []
        for item in skills:
            root = await self.load(item if isinstance(item, str) else item.skill_id)
            if root.lifecycle.state is not SkillLifecycleState.ACTIVE:
                raise SkillBundleError(
                    f"Skill {root.skill_id!r} is {root.lifecycle.state.value}, not ACTIVE"
                )
            roots.append(root)
        if not roots:
            raise SkillBundleError("at least one active Skill is required")
        catalog = await self._registry.all(states={SkillLifecycleState.ACTIVE})
        resolved = resolve_dependencies(roots, catalog)
        prompts: dict[str, str] = {}
        for skill in resolved:
            for key, value in skill.prompts.items():
                if prompts.setdefault(key, value) != value:
                    raise SkillBundleError(f"Skills define prompt {key!r} differently")
        capabilities = await self._resolve_capabilities(resolved)
        try:
            bundle = SkillBundle(
                skills=resolved,
                instructions=tuple(line for skill in resolved for line in skill.instructions),
                dependency_order=tuple(skill.skill_id for skill in resolved),
                dependencies=tuple(dep for skill in resolved for dep in skill.dependencies),
                capabilities=capabilities,
                resources=tuple(res for skill in resolved for res in skill.resources),
                prompts=prompts,
                provenance=tuple(skill.provenance for skill in resolved),
                metadata={"root_skill_ids": ",".join(skill.skill_id for skill in roots)},
            )
        except ValidationError as error:
            raise SkillBundleError("resolved Skills do not form a valid SkillBundle") from error
        await self._emit(
            "skill.bundle.built",
            root_count=len(roots),
            skill_count=len(bundle.skills),
            capability_count=len(bundle.capabilities),
        )
        await self._explain(
            "build_bundle",
            decision_type=DecisionType.CUSTOM,
            evidence_type=EvidenceType.RULE,
            summary=f"resolved {len(resolved)} Skills from {len(roots)} roots",
            dependency_order=list(bundle.dependency_order),
            capabilities=sorted(capabilities),
        )
        return bundle

    async def refresh(
        self,
        *,
        mode: RefreshMode | None = None,
        resource_ids: str | Iterable[str] = (),
        selector: ResourceSelector | None = None,
        trigger: TriggerSource = TriggerSource.MANUAL,
        metadata: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> RefreshResult | None:
        """Run the refresh engine, if any, then reload every Skill source.

        All arguments are passed to `RefreshEngine.refresh`. Healthy sources are
        committed even when another source fails.

        Returns:
            The refresh-engine result, or None without a refresh engine.

        Raises:
            SkillSourceError: If the refresh engine fails or any source fails.
        """
        result: RefreshResult | None = None
        if self._refresh_engine is not None:
            try:
                result = await self._refresh_engine.refresh(
                    mode=mode,
                    resource_ids=resource_ids,
                    selector=selector,
                    trigger=trigger,
                    metadata=metadata,
                    correlation_id=correlation_id,
                )
            except RefreshError as error:
                raise SkillSourceError("refresh-engine refresh failed") from error
            if result.status is RefreshStatus.FAILED:
                raise SkillSourceError("refresh-engine reported a failed Skill refresh")
        failed = await self._load_sources()
        await self._reindex_if_needed()
        self._capability_epoch += 1
        self._capabilities.clear()
        self._loaded = True
        await self._emit(
            "skill.refresh.completed",
            source_count=len(self._sources),
            external_engine=self._refresh_engine is not None,
            source_error_count=len(failed),
        )
        if failed:
            raise SkillSourceError(
                "one or more Skill sources failed; healthy sources were retained: "
                + ", ".join(sorted(failed))
            )
        return result

    async def schedule_refresh(
        self,
        interval: float,
        *,
        run_immediately: bool = False,
        events: EventPublisher | None = None,
    ) -> AsyncScheduler:
        """Start a refresh-engine `AsyncScheduler` that calls `refresh` every ``interval`` seconds.

        The manager owns the scheduler and stops it in `aclose`.

        Raises:
            SkillGovernanceError: If a scheduler is already running.
        """
        async with self._scheduler_lock:
            if self._scheduler is not None:
                raise SkillGovernanceError("a scheduled refresh is already running")

            async def scheduled_refresh() -> None:
                await self.refresh(trigger=TriggerSource.SCHEDULED)

            scheduler = AsyncScheduler(
                scheduled_refresh, interval, events=events, run_immediately=run_immediately
            )
            await scheduler.start()
            self._scheduler = scheduler
            return scheduler

    async def aclose(self) -> None:
        """Stop the owned scheduler and close the owned feedback manager.

        Injected collaborators stay open; their owner closes them.
        """
        async with self._scheduler_lock:
            if self._scheduler is not None:
                await self._scheduler.stop()
                self._scheduler = None
        if self._owns_feedback:
            await self._feedback.aclose()

    async def _decide(
        self,
        skill_id: str,
        *,
        approve: bool,
        reviewer: str | None,
        reason: str | None,
        metadata: Mapping[str, Any] | None,
    ) -> Skill:
        failure = SkillApprovalError if approve else SkillRejectionError
        decision = "approved" if approve else "rejected"
        details = dict(metadata or {})
        _reject_secret_keys(details)
        await self._ensure_loaded()
        async with self._lifecycle_locks(skill_id):
            skill = await self._registry.get(skill_id)
            if skill.lifecycle.state is not SkillLifecycleState.PENDING_APPROVAL:
                raise SkillLifecycleError(f"only a PENDING_APPROVAL Skill can be {decision}")
            if approve and skill.provenance.origin is SkillOrigin.AGENT:
                self._require_agent_creation()
            try:
                event = await self._feedback.submit(
                    source=FeedbackSource.HUMAN,
                    category=FeedbackCategory.APPROVAL if approve else FeedbackCategory.REJECTION,
                    target=FeedbackTarget(type=_SKILL_TARGET, id=skill_id),
                    payload={"decision": decision, "feedback": reason, "reviewer": reviewer},
                    metadata={"skill_revision": skill.revision, **details},
                )
                await self._feedback.acknowledge(event.feedback_id)
                await self._feedback.mark_handled(event.feedback_id)
            except FeedbackManagerError as error:
                raise failure(f"{decision} feedback failed for Skill {skill_id!r}") from error
            event_id = str(event.feedback_id)
            updated = skill.model_copy(
                update={
                    "lifecycle": SkillLifecycle(
                        state=SkillLifecycleState.ACTIVE
                        if approve
                        else SkillLifecycleState.REJECTED,
                        reason=reason,
                    ),
                    "governance": SkillGovernance(
                        approval_event_id=event_id if approve else None,
                        rejection_event_id=None if approve else event_id,
                        reviewer=reviewer,
                        reason=reason,
                    ),
                }
            )
            try:
                await self._replace_lifecycle(updated, previous=skill)
            except SkillManagerError as error:
                raise failure(f"Skill {skill_id!r} could not be {decision}") from error
            try:
                if approve:
                    await self._feedback.resolve(
                        event.feedback_id, resolution={"decision": decision}
                    )
                else:
                    await self._feedback.reject(event.feedback_id, reason=reason)
            except FeedbackManagerError as error:
                await self._replace_lifecycle(skill, previous=updated)
                raise failure(
                    f"{decision} feedback for Skill {skill_id!r} was not closed"
                ) from error
        logger.info("skill_reviewed", extra={"skill_id": skill_id, "decision": decision})
        await self._emit(
            f"skill.{decision}",
            skill_id=skill_id,
            skill_name=updated.metadata.name,
            skill_version=updated.metadata.version,
        )
        await self._explain(
            f"{'approve' if approve else 'reject'}_skill",
            decision_type=DecisionType.APPROVAL if approve else DecisionType.REJECTION,
            evidence_type=EvidenceType.POLICY,
            summary=f"human reviewer {decision} Skill {updated.metadata.name}",
            skill=updated,
            feedback_id=event_id,
            reviewer=reviewer or "",
        )
        return updated

    async def _rejections(self, parent: Skill) -> tuple[SkillFeedback, ...]:
        limit = self.config.feedback_context_limit
        if limit == 0:
            return ()
        events: Sequence[FeedbackEvent] = await self._feedback.query(
            FeedbackQuery(
                category=FeedbackCategory.REJECTION,
                target_type=_SKILL_TARGET,
                target_id=parent.skill_id,
                status=FeedbackStatus.REJECTED,
                limit=limit,
            )
        )
        return tuple(
            SkillFeedback(
                feedback_id=str(event.feedback_id),
                payload=dict(event.payload),
                metadata=dict(event.metadata),
                created_at=event.created_at,
            )
            for event in sorted(events, key=lambda item: item.created_at, reverse=True)
        )

    async def _resolve_capabilities(
        self, skills: Sequence[Skill]
    ) -> dict[str, tuple[Capability, ...]]:
        names = sorted({capability.name for skill in skills for capability in skill.capabilities})
        if not names:
            return {}
        runtime = self._mcp_runtime
        if runtime is None:
            raise CapabilityResolutionError(
                "Skills require MCP capabilities but no MCPRuntime was configured"
            )

        async def resolve(name: str) -> tuple[str, tuple[Capability, ...]]:
            cached = self._capabilities.get(name)
            if cached is not None:
                self._capabilities.move_to_end(name)
                return name, (cached,)
            epoch = self._capability_epoch
            try:
                candidates = await runtime.retrieve(
                    name, limit=self.config.capability_candidate_limit
                )
            except MCPCapabilityRouterError as error:
                raise CapabilityResolutionError(
                    f"MCP capability discovery failed for {name!r}"
                ) from error
            matches = [item for item in candidates if name in {item.name, item.capability_id}]
            if not matches:
                raise CapabilityResolutionError(f"required capability {name!r} was not found")
            selected = min(matches, key=lambda item: item.capability_id)
            if epoch == self._capability_epoch and self.config.capability_cache_size:
                self._capabilities[name] = selected
                while len(self._capabilities) > self.config.capability_cache_size:
                    self._capabilities.popitem(last=False)
            return name, (selected,)

        return dict(await asyncio.gather(*(resolve(name) for name in names)))

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._load_lock:
            if not self._loaded:
                await self._load_sources()
                await self._reindex_if_needed()
                self._loaded = True

    async def _load_sources(self) -> set[str]:
        results = await asyncio.gather(*(self._load_source(source) for source in self._sources))
        self._mark_index_dirty()
        return {key for keys in results for key in keys}

    async def _load_source(self, source: SkillSource) -> set[str]:
        prefix = source.source_id + ":"
        async with self._source_locks[source.source_id]:
            for key in [key for key in self._source_errors if key.startswith(prefix)]:
                del self._source_errors[key]
            try:
                documents = await source.load()
            except Exception as error:
                # One broken source must not hide the Skills of healthy sources.
                self._source_errors[source.source_id] = f"{type(error).__name__}: {error}"
                logger.warning("skill_source_load_failed", extra={"source_id": source.source_id})
                return {source.source_id}
            self._source_errors.pop(source.source_id, None)
            previous = self._documents_by_source.get(source.source_id, {})
            current: dict[str, str] = {}
            failed: set[str] = set()
            for locator, content in documents.items():
                try:
                    skill = await self._ingest(content)
                except (SkillManagerError, FeedbackManagerError) as error:
                    key = prefix + locator
                    self._source_errors[key] = f"{type(error).__name__}: {error}"
                    logger.warning("invalid_skill_ignored", extra={"source_id": source.source_id})
                    failed.add(key)
                    if locator in previous:
                        current[locator] = previous[locator]
                    continue
                self._source_for_skill[skill.skill_id] = source.source_id
                current[locator] = skill.skill_id
            kept = set(current.values())
            for skill_id in set(previous.values()) - kept:
                await self._drop(skill_id, source.source_id)
            self._documents_by_source[source.source_id] = current
        return failed

    async def _ingest(self, content: str) -> Skill:
        skill = await parse_skill_yaml(content, max_bytes=self.config.max_document_bytes)
        if skill.provenance.origin is SkillOrigin.AGENT:
            self._require_agent_creation()
            if (
                self.config.require_human_approval
                and skill.lifecycle.state is SkillLifecycleState.ACTIVE
                and not await self._approval_is_recorded(skill)
            ):
                skill = skill.model_copy(
                    update={"lifecycle": SkillLifecycle(state=SkillLifecycleState.PENDING_APPROVAL)}
                )
        skill = await self._validator.validate(skill)
        async with self._catalog_locks((skill.metadata.name, skill.metadata.version)):
            await self._registry.put(skill)
        return skill

    async def _drop(self, skill_id: str, source_id: str) -> None:
        if self._source_for_skill.get(skill_id) != source_id:
            return
        try:
            skill = await self._registry.get(skill_id)
            async with self._catalog_locks((skill.metadata.name, skill.metadata.version)):
                await self._registry.remove(skill_id)
        except SkillNotFoundError:
            pass
        self._source_for_skill.pop(skill_id, None)

    async def _approval_is_recorded(self, skill: Skill) -> bool:
        try:
            feedback_id = UUID(skill.governance.approval_event_id or "")
        except ValueError:
            return False
        event = await self._feedback.get(feedback_id)
        return (
            event is not None
            and event.target.type == _SKILL_TARGET
            and event.target.id == skill.skill_id
            and event.category == FeedbackCategory.APPROVAL
            and event.status is FeedbackStatus.RESOLVED
        )

    async def _reindex_if_needed(self) -> None:
        if not self._index_dirty:
            return
        async with self._reindex_lock:
            while self._index_dirty:
                version = self._catalog_version
                await self._discovery.index(await self._registry.all())
                if version == self._catalog_version:
                    self._index_dirty = False

    def _select_source(self, source_id: str | None) -> SkillSource | None:
        if source_id is None:
            return self._sources[0] if self._sources else None
        try:
            return self._source_by_id[source_id]
        except KeyError:
            raise SkillSourceError(f"unknown Skill source {source_id!r}") from None

    def _locked(
        self, skill: Skill, source: SkillSource | None
    ) -> AbstractAsyncContextManager[None]:
        @asynccontextmanager
        async def locked() -> AsyncGenerator[None]:
            async with AsyncExitStack() as stack:
                if source is not None:
                    await stack.enter_async_context(self._source_locks[source.source_id])
                await stack.enter_async_context(
                    self._catalog_locks((skill.metadata.name, skill.metadata.version))
                )
                yield

        return locked()

    async def _write(self, skill: Skill, source: SkillSource | None, *, persist: bool) -> None:
        async with self._locked(skill, source):
            await self._registry.check_put(skill)
            if source is not None and persist:
                await source.save(skill)
            try:
                await self._registry.put(skill)
            except SkillManagerError:
                if source is not None and persist:
                    await source.delete(skill.skill_id)
                raise
            if source is not None:
                self._source_for_skill[skill.skill_id] = source.source_id
        self._mark_index_dirty()

    async def _replace_lifecycle(self, skill: Skill, *, previous: Skill) -> None:
        source = self._source_by_id.get(self._source_for_skill.get(skill.skill_id, ""))
        async with self._locked(skill, source):
            current = await self._registry.get(skill.skill_id)
            if current != previous:
                raise SkillConflictError(
                    f"Skill {skill.skill_id!r} changed during a lifecycle transition"
                )
            if source is not None:
                await source.save(skill)
            try:
                await self._registry.replace_lifecycle(skill)
            except SkillManagerError:
                if source is not None:
                    await source.save(previous)
                raise
        self._mark_index_dirty()

    def _mark_index_dirty(self) -> None:
        self._catalog_version += 1
        self._index_dirty = True

    def _require_agent_creation(self) -> None:
        if not self.config.allow_agent_skill_creation:
            raise SkillCreationDisabledError("agent-generated Skill creation is disabled")

    async def _emit(self, name: str, **attributes: SkillObservabilityValue) -> None:
        try:
            await self._observability.emit(
                SkillObservabilityEvent(name=name, attributes=MappingProxyType(attributes))
            )
        except Exception as error:
            # Telemetry must never break a Skill operation.
            self._observability_errors.append(error)
            logger.exception("skill_observability_failed", extra={"event_name": name})

    async def _explain(
        self,
        action: str,
        *,
        decision_type: DecisionType,
        evidence_type: EvidenceType,
        summary: str,
        skill: Skill | None = None,
        **metadata: Any,
    ) -> None:
        if self._xai is None:
            return
        if skill is not None:
            metadata |= {
                "skill_id": skill.skill_id,
                "skill_name": skill.metadata.name,
                "skill_version": skill.metadata.version,
                "skill_revision": skill.revision,
                "lifecycle_state": skill.lifecycle.state.value,
            }
        try:
            await record_decision(
                self._xai,
                action,
                decision_type=decision_type,
                evidence_type=evidence_type,
                summary=summary,
                metadata=metadata,
            )
        except Exception as error:
            # Explanations must never break a Skill operation.
            self._observability_errors.append(error)
            logger.exception("skill_xai_failed", extra={"action": action})


__all__ = ["SkillManager"]
