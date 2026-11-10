"""Generate, reject, improve, approve and inspect a revision lineage."""

import asyncio

from _shared import SampleGenerator, show

from skill_manager import SkillManager, SkillManagerConfig


async def main() -> None:
    async with SkillManager(config=SkillManagerConfig(require_human_approval=True)) as manager:
        pending = await manager.generate_skill(SampleGenerator(), "Summarize safely")
        await manager.reject_skill(pending.skill_id, feedback="Include a privacy check.")
        revised = await manager.generate_skill(
            SampleGenerator(), "Apply reviewer feedback", parent_skill_id=pending.skill_id
        )
        approved = await manager.approve_skill(revised.skill_id, reviewer="example-reviewer")
        show(
            "Approved revision",
            {
                "revision": approved.revision,
                "state": approved.lifecycle.state.value,
                "parents": approved.provenance.parent_skill_ids,
            },
        )


if __name__ == "__main__":
    asyncio.run(main())
