"""Supply the same framework-agnostic SkillBundle to a deep agent."""

import asyncio

from _shared import chat_model, sample_skill, show
from deepagents import create_deep_agent

from skill_manager import SkillManager


async def main() -> None:
    async with chat_model() as model, SkillManager() as manager:
        await manager.register_skill(sample_skill())
        bundle = await manager.build_bundle(["summarize-ticket"])
        agent = create_deep_agent(
            model=model, tools=[], system_prompt="\n".join(bundle.instructions)
        )
        result = await agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Summarize: ticket #42 needs a password reset."}
                ]
            }
        )
        show("Deep agent answer", result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
