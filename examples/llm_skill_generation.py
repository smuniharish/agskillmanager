"""Generate a governed Skill using an OpenAI-compatible chat endpoint."""

import asyncio

from _shared import chat_model, show

from skill_manager import SkillManager, SkillManagerConfig
from skill_manager.integrations.langchain import XStructuredSkillGenerator


async def main() -> None:
    async with (
        chat_model() as model,
        SkillManager(config=SkillManagerConfig(require_human_approval=True)) as manager,
    ):
        pending = await manager.generate_skill(
            XStructuredSkillGenerator(model),
            "Create a skill named summarize-ticket, version 1.0.0, with safe support-ticket "
            "summarization instructions. No tools, dependencies or resources are required.",
        )
        show("Generated review candidate", pending.model_dump(mode="json"))


if __name__ == "__main__":
    asyncio.run(main())
