from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from agxai import XAIRuntime
from feedback_manager import FeedbackManager
from pydantic import ValidationError
from refresh_engine import (
    DiscoveryResult,
    RefreshEngine,
    RefreshError,
    RefreshRequest,
    RefreshResult,
    RefreshStatus,
    Resource,
    ResourceSnapshot,
    ResourceSource,
)

from skill_manager import (
    InMemorySkillRegistry,
    SkillBundleError,
    SkillGovernance,
    SkillLifecycleState,
    SkillManager,
    SkillManagerConfig,
    SkillOrigin,
    SkillSourceError,
    api,
    dump_skill_yaml,
)
from skill_manager.api import _KeyedLocks, _reject_secret_keys
from tests.helpers import MemorySource, StaticGenerator, StaticMCPRuntime, capability, make_skill


class EmptyResources(ResourceSource):
    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult([])

    async def snapshot(self, resource: Resource) -> ResourceSnapshot:
        return ResourceSnapshot(resource.resource_id, content="")


async def noop(*args: object) -> None:
    pass


async def test_refresh_engine_success_failure_and_forwarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = RefreshEngine(EmptyResources(), noop)
    async with SkillManager(refresh_engine=engine) as manager:
        result = await manager.refresh(metadata={"custom": True}, correlation_id="request")
        assert result is not None
        assert result.request.metadata == {"custom": True}
        now = datetime.now(UTC)
        monkeypatch.setattr(
            engine,
            "refresh",
            AsyncMock(
                return_value=RefreshResult(
                    refresh_id="failed",
                    request=RefreshRequest(),
                    status=RefreshStatus.FAILED,
                    started_at=now,
                    completed_at=now,
                    duration=0,
                )
            ),
        )
        with pytest.raises(SkillSourceError, match="reported"):
            await manager.refresh()
        monkeypatch.setattr(engine, "refresh", AsyncMock(side_effect=RefreshError("offline")))
        with pytest.raises(SkillSourceError, match="refresh-engine refresh failed"):
            await manager.refresh()


async def test_feedback_limit_and_approval_evidence() -> None:
    source = MemorySource()
    feedback = FeedbackManager()
    async with SkillManager(
        sources=[source],
        feedback_manager=feedback,
        config=SkillManagerConfig(require_human_approval=True, feedback_context_limit=0),
    ) as manager:
        pending = await manager.generate_skill(StaticGenerator(make_skill()), "x")
        assert await manager._rejections(pending) == ()
        unrecorded = pending.model_copy(
            update={"governance": SkillGovernance(approval_event_id=str(uuid4()))}
        )
        assert not await manager._approval_is_recorded(unrecorded)
        approved = await manager.approve_skill(pending.skill_id, metadata={"safe": ["text", 1]})
        assert await manager._approval_is_recorded(approved)
        await manager.refresh()
        assert (await manager.load(approved.skill_id)).lifecycle.state is SkillLifecycleState.ACTIVE
    await feedback.aclose()


async def test_unapproved_source_agents_are_held_for_review() -> None:
    agent = make_skill(origin=SkillOrigin.AGENT)
    source = MemorySource(documents={"agent": dump_skill_yaml(agent)})
    async with SkillManager(
        sources=[source], config=SkillManagerConfig(require_human_approval=True)
    ) as manager:
        assert (
            await manager.load(agent.skill_id)
        ).lifecycle.state is SkillLifecycleState.PENDING_APPROVAL


async def test_drop_guards_and_unpersisted_removal() -> None:
    registry = InMemorySkillRegistry()
    async with SkillManager(registry=registry) as manager:
        skill = await manager.register_skill(make_skill())
        await manager._drop(skill.skill_id, "other")
        assert await manager.load(skill.skill_id) == skill
        manager._source_for_skill[skill.skill_id] = "gone"
        await registry.remove(skill.skill_id)
        await manager._drop(skill.skill_id, "gone")
        skill = await manager.register_skill(make_skill())
        await manager.remove_skill(skill.skill_id)


async def test_bundle_validation_error_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SkillManager() as manager:
        skill = await manager.register_skill(make_skill())
        monkeypatch.setattr(api, "SkillBundle", AsyncMock())

        def invalid(**kwargs: object) -> None:
            raise ValidationError.from_exception_data("SkillBundle", [])

        monkeypatch.setattr(api, "SkillBundle", invalid)
        with pytest.raises(SkillBundleError, match="valid SkillBundle"):
            await manager.build_bundle([skill])


async def test_capability_refresh_during_retrieval_does_not_cache_stale_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = StaticMCPRuntime([capability("one")])
    async with SkillManager(mcp_runtime=runtime) as manager:
        skill = await manager.register_skill(make_skill(capabilities=["one"]))

        async def retrieve(*args: object, **kwargs: object) -> list:
            await manager.refresh()
            return runtime.capabilities

        monkeypatch.setattr(runtime, "retrieve", retrieve)
        await manager.build_bundle([skill])
        assert not manager._capabilities
    await runtime.close()


async def test_load_and_reindex_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    source = MemorySource()
    original_load = source.load

    async def delayed_load() -> dict:
        await asyncio.sleep(0)
        return dict(await original_load())

    monkeypatch.setattr(source, "load", delayed_load)
    async with SkillManager(sources=[source]) as manager:
        await asyncio.gather(manager.list_skills(), manager.list_skills())
        index = manager._discovery.index
        changed = False

        async def reindex(skills: tuple) -> None:
            nonlocal changed
            if not changed:
                manager._mark_index_dirty()
                changed = True
            await index(skills)

        monkeypatch.setattr(manager._discovery, "index", reindex)
        manager._mark_index_dirty()
        await manager._reindex_if_needed()
        assert not manager._index_dirty
        await manager._reindex_if_needed()


async def test_no_source_lifecycle_and_rejection_without_xai_errors() -> None:
    runtime = XAIRuntime()
    async with SkillManager(
        xai_runtime=runtime, config=SkillManagerConfig(require_human_approval=True)
    ) as manager:
        pending = await manager.generate_skill(StaticGenerator(make_skill()), "x")
        await manager.reject_skill(pending.skill_id, feedback="revise")
        assert manager.observability_errors == ()
    await runtime.close()


async def test_new_invalid_document_and_source_free_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with SkillManager(sources=[MemorySource(documents={"bad": "invalid"})]) as manager:
        await manager.list_skills()
        assert "memory:bad" in manager.source_errors
    registry = InMemorySkillRegistry()
    async with SkillManager(registry=registry) as manager:
        with monkeypatch.context() as patch:
            patch.setattr(registry, "put", AsyncMock(side_effect=api.SkillConflictError("race")))
            with pytest.raises(api.SkillConflictError):
                await manager.register_skill(make_skill())
        skill = await manager.register_skill(make_skill())
        monkeypatch.setattr(
            registry, "replace_lifecycle", AsyncMock(side_effect=api.SkillConflictError("race"))
        )
        with pytest.raises(api.SkillConflictError):
            await manager._replace_lifecycle(skill, previous=skill)


def test_keyed_lock_reuse_and_nested_safe_metadata() -> None:
    locks = _KeyedLocks()
    first = locks("one")
    assert locks("one") is first
    _reject_secret_keys({"plain": 1, "list": [1, {"safe": True}], "nested": {"safe": True}})
