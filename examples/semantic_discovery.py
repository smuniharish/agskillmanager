"""Add semantic search and reranking with custom RetrievalLoom components."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from _shared import sample_skill, show
from retrievalloom import Components
from retrievalloom.contracts.component import ComponentInfo, make_info
from retrievalloom.contracts.models import EmbeddingModelABC, RerankerABC, RerankScore

from skill_manager import RetrievalLoomDiscoveryProvider, SkillManager

if TYPE_CHECKING:
    from collections.abc import Sequence

    from retrievalloom.contracts.models import RerankItem

VOCABULARY = ("ticket", "invoice")


class VocabularyEmbedding(EmbeddingModelABC):
    _info = make_info(
        component="embedding",
        implementation="vocabulary",
        version="1",
        model_identity="vocabulary-" + "-".join(VOCABULARY),
        dimensions=len(VOCABULARY),
    )

    @property
    def info(self) -> ComponentInfo:
        return self._info

    @property
    def dimensions(self) -> int:
        return len(VOCABULARY)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [await self.embed_query(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(text.lower().count(word)) + 0.01 for word in VOCABULARY]


class OverlapReranker(RerankerABC):
    _info = make_info(component="reranker", implementation="overlap", version="1")

    @property
    def info(self) -> ComponentInfo:
        return self._info

    async def rerank(self, query: str, items: Sequence[RerankItem]) -> list[RerankScore]:
        terms = set(re.findall(r"\w+", query.lower()))
        return [
            RerankScore(
                item_id=item.item_id,
                score=float(len(terms & set(re.findall(r"\w+", item.text.lower())))),
            )
            for item in items
        ]


async def main() -> None:
    discovery = RetrievalLoomDiscoveryProvider(
        components=Components(embedding=VocabularyEmbedding(), reranker=OverlapReranker()),
        candidate_pool_size=10,
    )
    try:
        async with SkillManager(discovery=discovery) as manager:
            await manager.register_skill(sample_skill("summarize-ticket"))
            await manager.register_skill(sample_skill("explain-invoice"))
            show(
                "Semantic matches",
                [s.metadata.name for s in await manager.discover("invoice", top_k=1)],
            )
    finally:
        await discovery.aclose()


if __name__ == "__main__":
    asyncio.run(main())
