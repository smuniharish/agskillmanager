"""Refresh an external catalog and schedule managed background refreshes."""

from __future__ import annotations

import asyncio

from _shared import show
from refresh_engine import (
    DiscoveryResult,
    PlanAction,
    RefreshEngine,
    RefreshRequest,
    Resource,
    ResourceSnapshot,
    ResourceSource,
)

from skill_manager import SkillManager


class CatalogResources(ResourceSource):
    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult([Resource("skills")])

    async def snapshot(self, resource: Resource) -> ResourceSnapshot:
        return ResourceSnapshot(resource.resource_id, content={"catalog_version": 1})


async def apply_refresh(
    resource: Resource,
    snapshot: ResourceSnapshot | None,
    action: PlanAction,
    request: RefreshRequest,
) -> None:
    show("Catalog refreshed", {"resource": resource.resource_id})


async def main() -> None:
    engine = RefreshEngine(CatalogResources(), apply_refresh)
    try:
        async with SkillManager(refresh_engine=engine) as manager:
            result = await manager.refresh()
            show("Refresh status", result.status.value if result is not None else "source-only")
            await manager.schedule_refresh(3600)
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
