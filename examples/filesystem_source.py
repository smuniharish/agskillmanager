"""Write to multiple sources, then load them through a new manager."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from _shared import sample_skill, show

from skill_manager import FilesystemSkillSource, SkillManager


async def main() -> None:
    with TemporaryDirectory() as directory:
        sources = [
            FilesystemSkillSource(Path(directory) / "team", source_id="team"),
            FilesystemSkillSource(Path(directory) / "shared", source_id="shared"),
        ]
        async with SkillManager(sources=sources) as manager:
            await manager.register_skill(sample_skill(), source_id="team")
            await manager.register_skill(sample_skill("privacy"), source_id="shared")
        async with SkillManager(sources=sources) as manager:
            show("Reloaded catalog", [item.metadata.name for item in await manager.list_skills()])


if __name__ == "__main__":
    asyncio.run(main())
