"""Resolve a Skill's MCP requirements against a live server."""

import asyncio
import os

from _shared import sample_skill, show
from mcp_capability_router import MCPRuntime

from skill_manager import SkillCapability, SkillManager


async def main() -> None:
    async with MCPRuntime() as runtime:
        await runtime.register_mcp(
            "tools", os.getenv("SKILL_MANAGER_MCP_URL", "http://127.0.0.1:8765/mcp")
        )
        await runtime.refresh_server("tools")
        async with SkillManager(mcp_runtime=runtime) as manager:
            skill = await manager.register_skill(
                sample_skill(capabilities=(SkillCapability(name="github.pull_request.read"),))
            )
            bundle = await manager.build_bundle([skill])
            show("Resolved MCP capabilities", sorted(bundle.capabilities))


if __name__ == "__main__":
    asyncio.run(main())
