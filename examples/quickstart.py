"""Register, discover and compose a Skill with transitive dependencies."""

import asyncio

from _shared import sample_skill, show

from skill_manager import SkillDependency, SkillManager


async def main() -> None:
    async with SkillManager() as manager:
        await manager.register_skill(sample_skill("privacy"))
        await manager.register_skill(sample_skill(dependencies=(SkillDependency(name="privacy"),)))
        matches = await manager.discover("summarize ticket", top_k=1)
        bundle = await manager.build_bundle(matches)
        show("Dependency order", [item.metadata.name for item in bundle.skills])
        show("Instructions", bundle.instructions)


if __name__ == "__main__":
    asyncio.run(main())
