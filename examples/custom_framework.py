"""A plain-Python agent consumes instructions without any framework adapter."""

import asyncio

from _shared import sample_skill, show

from skill_manager import SkillManager


async def main() -> None:
    async with SkillManager() as manager:
        await manager.register_skill(sample_skill())
        bundle = await manager.build_bundle(["summarize-ticket"])
        system_prompt = "\n".join(bundle.instructions)
        show(
            "Plain Python agent context", {"system": system_prompt, "task": "Summarize ticket #42"}
        )


if __name__ == "__main__":
    asyncio.run(main())
