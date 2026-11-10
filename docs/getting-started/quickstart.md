# Quickstart

```python
import asyncio

from skill_manager import Skill, SkillDependency, SkillManager, SkillMetadata


async def main() -> None:
    async with SkillManager() as manager:
        privacy = Skill(
            metadata=SkillMetadata(
                name="privacy", version="1.0.0", description="Protect customer data."
            ),
            instructions=("Remove personal information.",),
        )
        summarize = Skill(
            metadata=SkillMetadata(
                name="summarize-ticket", version="1.0.0", description="Summarize support tickets."
            ),
            instructions=("Use supplied facts only.",),
            dependencies=(SkillDependency(name="privacy", version=">=1,<2"),),
        )
        await manager.register_skill(privacy)
        await manager.register_skill(summarize)
        matches = await manager.discover("summarize support ticket", top_k=1)
        bundle = await manager.build_bundle(matches)
        print([skill.metadata.name for skill in bundle.skills])
        print("\n".join(bundle.instructions))


asyncio.run(main())
```

The dependency precedes the root in the bundle. Registration does not execute
instructions, and discovery returns only active Skills.

The default catalog is in memory. Add [persistent storage](../guide/storage.md)
to retain it across restarts.
