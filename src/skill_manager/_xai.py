"""Record Skill governance decisions into an agxai `XAIRuntime`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from agxai import DecisionType, EvidenceType, XAIRuntime


async def record_decision(
    runtime: XAIRuntime,
    action: str,
    *,
    decision_type: DecisionType,
    evidence_type: EvidenceType,
    summary: str,
    metadata: Mapping[str, Any],
) -> None:
    """Record one evidence item and the decision it supports.

    The records join the run active in the current context; without one, a
    dedicated run wraps them so every decision is still explained.
    """
    run = runtime.current_run
    owned = run is None
    if run is None:
        run = await runtime.start_run({"component": "agskillmanager", "operation": action})
    error: BaseException | None = None
    try:
        evidence = await runtime.record_evidence(
            evidence_type, summary=summary, metadata=metadata, run=run
        )
        await runtime.record_decision(
            action,
            decision_type=decision_type,
            evidence_ids=[evidence.id],
            metadata=metadata,
            run=run,
        )
    except BaseException as caught:
        error = caught
        raise
    finally:
        if owned:
            await runtime.finish_run(run, error)
