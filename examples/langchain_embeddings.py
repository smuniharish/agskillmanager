"""Adapt any LangChain Embeddings implementation to semantic retrieval."""

import asyncio

from _shared import sample_skill, show
from langchain_core.embeddings import DeterministicFakeEmbedding

from skill_manager import PipelineDiscoveryProvider, SemanticSkillRetriever, SkillManager
from skill_manager.integrations.langchain import LangChainEmbedder


async def main() -> None:
    embedder = LangChainEmbedder(DeterministicFakeEmbedding(size=32))
    discovery = PipelineDiscoveryProvider(SemanticSkillRetriever(embedder))
    async with SkillManager(discovery=discovery) as manager:
        await manager.register_skill(sample_skill())
        matches = await manager.discover("summarize ticket", top_k=1)
        show("LangChain embeddings", [s.metadata.name for s in matches])


if __name__ == "__main__":
    asyncio.run(main())
