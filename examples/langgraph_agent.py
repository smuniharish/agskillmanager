"""Pass a resolved SkillBundle into a LangGraph node."""

from __future__ import annotations

import asyncio

from _shared import chat_model, sample_skill, show
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from skill_manager import SkillManager


class State(BaseModel):
    task: str
    answer: str


async def main() -> None:
    async with chat_model() as model, SkillManager() as manager:
        await manager.register_skill(sample_skill())
        bundle = await manager.build_bundle(["summarize-ticket"])

        async def summarize(state: State) -> dict[str, str]:
            response = await model.ainvoke(
                [
                    SystemMessage(content="\n".join(bundle.instructions)),
                    HumanMessage(content=state.task),
                ]
            )
            return {"answer": response.text}

        graph = StateGraph(State)
        graph.add_node("summarize", summarize)
        graph.add_edge(START, "summarize")
        graph.add_edge("summarize", END)
        result = await graph.compile().ainvoke(
            {"task": "Ticket #42: the customer cannot reset their password.", "answer": ""}
        )
        show("LangGraph answer", result["answer"])


if __name__ == "__main__":
    asyncio.run(main())
