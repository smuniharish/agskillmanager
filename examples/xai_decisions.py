"""Collect and explain Skill generation and bundle decisions with agxai."""

import asyncio

from _shared import SampleGenerator, show
from agxai import XAIRuntime

from skill_manager import SkillManager


async def main() -> None:
    runtime = XAIRuntime()
    try:
        with runtime.collect_runs() as runs:
            async with SkillManager(xai_runtime=runtime) as manager:
                skill = await manager.generate_skill(SampleGenerator(), "Summarize safely")
                await manager.build_bundle([skill])
        for run in runs:
            for decision in run.decisions:
                explanation = await runtime.explain_decision(decision, run=run)
                show("Decision explanation", explanation.model_dump(mode="json"))
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
