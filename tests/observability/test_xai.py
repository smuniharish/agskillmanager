from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from agxai import DecisionType, EvidenceType, XAIRuntime

from skill_manager import SkillManager
from skill_manager._xai import record_decision
from tests.helpers import StaticGenerator, make_skill


async def test_decisions_join_current_run_or_create_their_own() -> None:
    runtime = XAIRuntime()
    with runtime.collect_runs() as runs:
        async with SkillManager(xai_runtime=runtime) as manager:
            skill = await manager.generate_skill(StaticGenerator(make_skill()), "summarize")
            await manager.build_bundle([skill])
            run = await runtime.start_run({"test": True})
            with runtime.activate_run(run):
                await manager.build_bundle([skill])
            await runtime.finish_run(run)
            assert manager.observability_errors == ()
    assert len(runs) == 3
    await runtime.close()


async def test_recording_failure_finishes_owned_run(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = XAIRuntime()
    monkeypatch.setattr(runtime, "record_evidence", AsyncMock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError, match="offline"):
        await record_decision(
            runtime,
            "test",
            decision_type=DecisionType.CUSTOM,
            evidence_type=EvidenceType.RULE,
            summary="test",
            metadata={},
        )
    assert runtime.current_run is None
    async with SkillManager(xai_runtime=runtime) as manager:
        await manager.generate_skill(StaticGenerator(make_skill()), "x")
        assert len(manager.observability_errors) == 1
    await runtime.close()
