"""Discover Skills with local bge-m3, bge-reranker-v2-m3 and NLI models.

Run ``uv sync --group models`` and place the models under ``models/`` (or set
``MODELS_DIR``). The engine combines keyword, fuzzy, BM25 and bge-m3 dense
search, reranks with the cross-encoder, and checks claims with the NLI model.
"""

import asyncio

from _local_models import BgeM3Embedding, BgeReranker, LocalNLI, models_available
from _shared import show
from retrievalloom import Components, EngineConfig, NLIConfig, RetrievalConfig

from skill_manager import RetrievalLoomDiscoveryProvider, Skill, SkillManager, SkillMetadata

CATALOG = {
    "refund-card-payment": "Refund a card payment and return money to the customer.",
    "reset-password": "Help a user regain access when they forgot their login credentials.",
    "explain-invoice": "Explain each line of an invoice, including taxes and discounts.",
    "export-customer-data": "Export and delete a customer's personal data on request.",
}


def skill(name: str, description: str) -> Skill:
    return Skill(
        metadata=SkillMetadata(name=name, version="1.0.0", description=description),
        instructions=(description,),
    )


async def main() -> None:
    if not models_available():
        raise SystemExit("Place bge-m3, bge-reranker-v2-m3 and nli/ models under MODELS_DIR.")
    discovery = RetrievalLoomDiscoveryProvider(
        config=EngineConfig(retrieval=RetrievalConfig(nli=NLIConfig(enabled=True))),
        components=Components(embedding=BgeM3Embedding(), reranker=BgeReranker(), nli=LocalNLI()),
    )
    try:
        async with SkillManager(discovery=discovery) as manager:
            for name, description in CATALOG.items():
                await manager.register_skill(skill(name, description))
            paraphrases = {
                query: [s.metadata.name for s in await manager.discover(query, top_k=1)]
                for query in (
                    "How do I get my money back?",
                    "I can't sign in anymore",
                    "Wie lese ich meine Rechnung?",
                )
            }
            show("Local model discovery", paraphrases)
            result = await discovery.engine.retrieve(
                "customer data",
                scope=discovery.scope,
                top_k=1,
                claims=["This Skill never deletes customer data."],
            )
            show(
                "NLI claim check",
                [
                    {
                        "skill": item.sources[0].title,
                        "contradicts_claim": bool(
                            item.nli_summary and item.nli_summary.has_contradiction
                        ),
                    }
                    for item in result.evidence[:1]
                ],
            )
    finally:
        await discovery.aclose()


if __name__ == "__main__":
    asyncio.run(main())
