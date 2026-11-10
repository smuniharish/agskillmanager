"""Copyable framework-free integration."""

import asyncio

from skill_manager import Skill, SkillManager, SkillMetadata


async def main() -> None:
    async with SkillManager() as manager:
        skill = await manager.register_skill(
            Skill(
                metadata=SkillMetadata(
                    name="review-ticket", version="1.0.0", description="Review support tickets."
                ),
                instructions=("Use verified facts.", "Remove personal information."),
            )
        )
        bundle = await manager.build_bundle([skill])
        print("\n".join(bundle.instructions))


if __name__ == "__main__":
    asyncio.run(main())
