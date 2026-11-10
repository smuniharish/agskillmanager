"""Use a custom asynchronous embedding provider and reranker."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from _shared import sample_skill, show
from mcp_capability_router import Embedder

from skill_manager import (
    PipelineDiscoveryProvider,
    SemanticSkillRetriever,
    SkillManager,
    SkillReranker,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from skill_manager import RetrievedSkill, Skill


class VocabularyEmbedder(Embedder):
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [await self.embed_query(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(text.lower().count(word)) for word in ("ticket", "invoice")]


class ScoreReranker(SkillReranker):
    async def rerank(
        self, query: str, candidates: Sequence[RetrievedSkill], *, top_k: int
    ) -> list[Skill]:
        return [item.skill for item in sorted(candidates, key=lambda item: -item.score)[:top_k]]


async def main() -> None:
    discovery = PipelineDiscoveryProvider(
        SemanticSkillRetriever(VocabularyEmbedder()),
        reranker=ScoreReranker(),
        candidate_pool_size=10,
    )
    async with SkillManager(discovery=discovery) as manager:
        await manager.register_skill(sample_skill("summarize-ticket"))
        await manager.register_skill(sample_skill("explain-invoice"))
        show(
            "Semantic matches",
            [s.metadata.name for s in await manager.discover("invoice", top_k=1)],
        )


if __name__ == "__main__":
    asyncio.run(main())
