from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from feedback_manager import FeedbackManager, FeedbackManagerError
from mcp_capability_router import MCPCapabilityRouterError

from skill_manager import (
    CapabilityResolutionError,
    InMemorySkillRegistry,
    SkillApprovalError,
    SkillBundleError,
    SkillConflictError,
    SkillCreationDisabledError,
    SkillDependency,
    SkillGovernanceError,
    SkillLifecycleState,
    SkillManager,
    SkillManagerConfig,
    SkillNotFoundError,
    SkillOrigin,
    SkillRejectionError,
    SkillSourceError,
    dump_skill_yaml,
)
from skill_manager.errors import SkillLifecycleError
from tests.helpers import (
    MemorySource,
    RecordingSink,
    StaticGenerator,
    StaticMCPRuntime,
    capability,
    make_skill,
)


async def test_register_discover_bundle_remove() -> None:
    source = MemorySource()
    sink = RecordingSink()
    async with SkillManager(sources=[source], observability_sink=sink) as manager:
        base = await manager.register_skill(make_skill("base"))
        root = await manager.register_skill(
            make_skill(
                "root", dependencies=[SkillDependency(name="base")], prompts={"system": "hi"}
            )
        )
        assert await manager.load(root.skill_id) == root
        assert await manager.load("root") == root
        assert await manager.discover("root") == [root]
        bundle = await manager.build_bundle([root])
        assert bundle.dependency_order == (base.skill_id, root.skill_id)
        assert bundle.prompts == {"system": "hi"}
        assert await manager.list_skills(origins=[SkillOrigin.AGENT]) == ()
        assert len(await manager.list_skills()) == 2
        await manager.remove_skill(root.skill_id)
        with pytest.raises(SkillNotFoundError):
            await manager.load(root.skill_id)
    assert not source.closed
    assert "skill.bundle.built" in sink.names()


async def test_approval_rejection_and_regeneration() -> None:
    source = MemorySource()
    feedback = FeedbackManager()
    async with SkillManager(
        sources=[source],
        feedback_manager=feedback,
        config=SkillManagerConfig(require_human_approval=True),
    ) as manager:
        generator = StaticGenerator(make_skill())
        pending = await manager.generate_skill(generator, "summarize")
        assert pending.lifecycle.state is SkillLifecycleState.PENDING_APPROVAL
        assert source.documents == {}
        assert await manager.list_pending_skills() == (pending,)
        with pytest.raises(SkillBundleError):
            await manager.build_bundle([pending])
        rejected = await manager.reject_skill(pending.skill_id, feedback="Add privacy rules")
        with pytest.raises(SkillLifecycleError):
            await manager.remove_skill(rejected.skill_id)
        revised = await manager.generate_skill(
            generator, "improve", parent_skill_id=rejected.skill_id
        )
        assert revised.revision == 2
        assert revised.provenance.parent_skill_ids == (rejected.skill_id,)
        assert generator.requests[-1].feedback[0].payload["feedback"] == "Add privacy rules"
        approved = await manager.approve_skill(revised.skill_id, reviewer="reviewer", reason="ok")
        assert approved.lifecycle.state is SkillLifecycleState.ACTIVE
        assert approved.skill_id in source.documents
        await manager.refresh()
        assert await manager.load(approved.skill_id) == approved
        with pytest.raises(SkillLifecycleError):
            await manager.approve_skill(approved.skill_id)
        with pytest.raises(SkillRejectionError, match="empty"):
            await manager.reject_skill(approved.skill_id, feedback=" ")
    await feedback.aclose()


async def test_governance_and_secret_metadata() -> None:
    async with SkillManager(config=SkillManagerConfig(allow_agent_skill_creation=False)) as manager:
        with pytest.raises(SkillCreationDisabledError):
            await manager.generate_skill(StaticGenerator(make_skill()), "x")
        with pytest.raises(SkillCreationDisabledError):
            await manager.register_skill(make_skill(origin=SkillOrigin.AGENT))
    async with SkillManager() as manager:
        with pytest.raises(SkillGovernanceError):
            await manager.register_skill(
                make_skill(origin=SkillOrigin.AGENT, state=SkillLifecycleState.PENDING_APPROVAL)
            )
        for metadata in (
            {"api_key": "x"},
            {"nested": {"token": "x"}},
            {"nested": [1, {"authorization": "x"}]},
        ):
            with pytest.raises(SkillGovernanceError):
                await manager.approve_skill("not-found", metadata=metadata)
        with pytest.raises(SkillSourceError, match="unknown"):
            await manager.register_skill(make_skill(), source_id="missing")
    with pytest.raises(ValueError, match="unique"):
        SkillManager(sources=[MemorySource(), MemorySource()])


async def test_sources_isolate_errors_retain_last_good_and_drop_removed() -> None:
    skill = make_skill()
    good = MemorySource("good", documents={"one": dump_skill_yaml(skill)})
    bad = MemorySource("bad")
    bad.fail_load = RuntimeError("offline")
    async with SkillManager(sources=[good, bad]) as manager:
        assert await manager.load(skill.skill_id) == skill
        assert "bad" in manager.source_errors
        with pytest.raises(SkillSourceError):
            await manager.load("absent")
        good.documents["one"] = "invalid: yaml"
        with pytest.raises(SkillSourceError):
            await manager.refresh()
        assert await manager.load(skill.skill_id) == skill
        assert "good:one" in manager.source_errors
        good.documents.clear()
        bad.fail_load = None
        await manager.refresh()
        assert manager.source_errors == {}
        with pytest.raises(SkillNotFoundError):
            await manager.load(skill.skill_id)


async def test_bundle_guards() -> None:
    async with SkillManager() as manager:
        with pytest.raises(SkillBundleError, match="at least"):
            await manager.build_bundle([])
        first = await manager.register_skill(make_skill("first", prompts={"system": "one"}))
        second = await manager.register_skill(make_skill("second", prompts={"system": "two"}))
        with pytest.raises(SkillBundleError, match="differently"):
            await manager.build_bundle([first, second])


async def test_capabilities_cache_refresh_and_errors() -> None:
    skill = make_skill(capabilities=["tickets.read"])
    async with SkillManager() as manager:
        await manager.register_skill(skill)
        with pytest.raises(CapabilityResolutionError, match="no MCPRuntime"):
            await manager.build_bundle([skill])
    runtime = StaticMCPRuntime([capability("tickets.read", "b"), capability("tickets.read", "a")])
    async with SkillManager(mcp_runtime=runtime) as manager:
        await manager.register_skill(skill)
        bundle = await manager.build_bundle([skill])
        assert bundle.capabilities["tickets.read"][0].capability_id == "a"
        await manager.build_bundle([skill])
        assert runtime.queries == ["tickets.read"]
        await manager.refresh()
        runtime.capabilities = []
        with pytest.raises(CapabilityResolutionError, match="not found"):
            await manager.build_bundle([skill])
        runtime.error = MCPCapabilityRouterError("offline")
        with pytest.raises(CapabilityResolutionError, match="discovery failed"):
            await manager.build_bundle([skill])
    await runtime.close()


async def test_cache_eviction_and_disabled_cache() -> None:
    for size in (0, 1):
        runtime = StaticMCPRuntime([capability("one"), capability("two")])
        async with SkillManager(
            mcp_runtime=runtime, config=SkillManagerConfig(capability_cache_size=size)
        ) as manager:
            skill = await manager.register_skill(make_skill(capabilities=["one", "two"]))
            await manager.build_bundle([skill])
            assert len(manager._capabilities) == size
        await runtime.close()


@pytest.mark.parametrize("approve", [True, False])
@pytest.mark.parametrize("stage", ["submit", "close", "persist"])
async def test_review_failures_preserve_pending(
    approve: bool, stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = MemorySource()
    feedback = FeedbackManager()
    async with SkillManager(
        sources=[source],
        feedback_manager=feedback,
        config=SkillManagerConfig(require_human_approval=True),
    ) as manager:
        pending = await manager.generate_skill(StaticGenerator(make_skill()), "x")
        if stage == "persist":
            source.fail_save = SkillSourceError("offline")
        else:
            method = "submit" if stage == "submit" else ("resolve" if approve else "reject")
            monkeypatch.setattr(
                feedback, method, AsyncMock(side_effect=FeedbackManagerError("offline"))
            )
        operation = (
            manager.approve_skill(pending.skill_id)
            if approve
            else manager.reject_skill(pending.skill_id, feedback="fix")
        )
        with pytest.raises(SkillApprovalError if approve else SkillRejectionError):
            await operation
        assert (
            await manager.load(pending.skill_id)
        ).lifecycle.state is SkillLifecycleState.PENDING_APPROVAL
    await feedback.aclose()


async def test_write_and_lifecycle_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    source = MemorySource()
    registry = InMemorySkillRegistry()
    async with SkillManager(sources=[source], registry=registry) as manager:
        with monkeypatch.context() as patch:
            patch.setattr(registry, "put", AsyncMock(side_effect=SkillConflictError("race")))
            with pytest.raises(SkillConflictError):
                await manager.register_skill(make_skill())
            assert source.documents == {}
        skill = await manager.register_skill(make_skill())
        with pytest.raises(SkillConflictError, match="changed"):
            await manager._replace_lifecycle(skill, previous=make_skill())
        monkeypatch.setattr(
            registry, "replace_lifecycle", AsyncMock(side_effect=SkillConflictError("race"))
        )
        with pytest.raises(SkillConflictError):
            await manager._replace_lifecycle(skill, previous=skill)
        assert source.documents[skill.skill_id] == dump_skill_yaml(skill)


async def test_scheduler_and_observability_errors() -> None:
    async with SkillManager(observability_sink=RecordingSink(fail=True)) as manager:
        await manager.register_skill(make_skill())
        assert len(manager.observability_errors) == 1
        await manager.schedule_refresh(3600, run_immediately=True)
        await asyncio.sleep(0.05)
        with pytest.raises(SkillGovernanceError, match="already"):
            await manager.schedule_refresh(3600)
    assert manager._scheduler is None
