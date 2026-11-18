"""Adapt any LangChain Embeddings implementation to semantic Skill discovery."""

import asyncio

from _shared import sample_skill, show
from langchain_core.embeddings import DeterministicFakeEmbedding
from retrievalloom import Components

from skill_manager import RetrievalLoomDiscoveryProvider, SkillManager
from skill_manager.integrations.langchain import LangChainEmbeddingModel


async def main() -> None:
    embedding = LangChainEmbeddingModel(DeterministicFakeEmbedding(size=32), dimensions=32)
    discovery = RetrievalLoomDiscoveryProvider(components=Components(embedding=embedding))
    try:
        async with SkillManager(discovery=discovery) as manager:
            await manager.register_skill(sample_skill())
            matches = await manager.discover("summarize ticket", top_k=1)
            show("LangChain embeddings", [s.metadata.name for s in matches])
    finally:
        await discovery.aclose()


if __name__ == "__main__":
    asyncio.run(main())
