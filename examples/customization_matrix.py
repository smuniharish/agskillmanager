"""Inject fully configured collaborators without losing downstream options."""

import asyncio
from tempfile import TemporaryDirectory

from _shared import SampleGenerator, show
from agxai import XAIRuntime
from feedback_manager import FeedbackManager
from mcp_capability_router import InMemoryRegistry, MCPRuntime
from refresh import CatalogResources, apply_refresh
from refresh_engine import InMemoryStateStore, RefreshEngine

from skill_manager import (
    DefaultSkillValidator,
    FilesystemSkillSource,
    InMemorySkillRegistry,
    PipelineDiscoveryProvider,
    SkillManager,
    SkillManagerConfig,
    SkillObservabilityEvent,
    SkillObservabilitySink,
)


class EventRecorder(SkillObservabilitySink):
    def __init__(self) -> None:
        self.names: list[str] = []

    async def emit(self, event: SkillObservabilityEvent) -> None:
        self.names.append(event.name)


async def main() -> None:
    feedback = FeedbackManager(learning=False)
    mcp = MCPRuntime(registry=InMemoryRegistry(), max_concurrency=4)
    refresh = RefreshEngine(CatalogResources(), apply_refresh, store=InMemoryStateStore())
    xai = XAIRuntime(application_id="skill-customization", tenant_id="example")
    events = EventRecorder()
    try:
        with TemporaryDirectory() as root:
            async with SkillManager(
                sources=[FilesystemSkillSource(root)],
                registry=InMemorySkillRegistry(),
                discovery=PipelineDiscoveryProvider(candidate_pool_size=25),
                validator=DefaultSkillValidator(),
                config=SkillManagerConfig(require_human_approval=True),
                feedback_manager=feedback,
                mcp_runtime=mcp,
                refresh_engine=refresh,
                xai_runtime=xai,
                observability_sink=events,
            ) as manager:
                pending = await manager.generate_skill(SampleGenerator(), "summarize")
                approved = await manager.approve_skill(pending.skill_id)
                await manager.build_bundle([approved])
                await manager.refresh()
                show("Injected collaborators", {"events": events.names})
    finally:
        await feedback.aclose()
        await mcp.close()
        await refresh.close()
        await xai.close()


if __name__ == "__main__":
    asyncio.run(main())
