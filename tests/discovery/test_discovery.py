from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from skill_manager import (
    LexicalSkillRetriever,
    PipelineDiscoveryProvider,
    RetrievedSkill,
    ScoreSkillReranker,
    SemanticSkillRetriever,
    Skill,
    SkillDiscoveryError,
    SkillLifecycleState,
    SkillReranker,
    SkillRetriever,
    matches_filters,
    skill_document,
    validate_filters,
)
from tests.helpers import KeywordEmbedder, make_skill

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

TICKET = make_skill(
    "summarize-ticket",
    description="Summarize a support ticket.",
    tags=("support",),
    capabilities=("tickets.read",),
)
INVOICE = make_skill("explain-invoice", description="Explain an invoice line.", tags=("billing",))
DEPLOY = make_skill("deploy-service", description="Deploy a service.", version="2.0.0")
PENDING = make_skill(
    "ticket-draft", description="Draft ticket.", state=SkillLifecycleState.PENDING_APPROVAL
)
CATALOG = (TICKET, INVOICE, DEPLOY, PENDING)


def test_filters() -> None:
    validate_filters(None)
    validate_filters({"name": "x", "version": "1", "tag": "t", "capability": "c"})
    with pytest.raises(SkillDiscoveryError, match="owner"):
        validate_filters({"owner": "me"})
    assert matches_filters(TICKET, None)
    assert matches_filters(TICKET, {"tag": "support", "capability": "tickets.read"})
    assert matches_filters(DEPLOY, {"name": "deploy-service", "version": "2.0.0"})
    assert not matches_filters(TICKET, {"tag": "billing"})
    assert not matches_filters(PENDING, None)


def test_skill_document_includes_searchable_fields() -> None:
    document = skill_document(TICKET)
    for text in ("summarize-ticket", "support ticket", "support", "tickets.read"):
        assert text in document


async def test_lexical_retrieval_scores_by_matched_terms() -> None:
    retriever = LexicalSkillRetriever()
    await retriever.index(CATALOG)
    results = await retriever.retrieve("summarize the support ticket", limit=5)
    assert results[0].skill == TICKET
    assert results[0].score >= 2
    assert all(item.skill != PENDING for item in results)
    everything = await retriever.retrieve("   ", limit=10)
    assert {item.skill.skill_id for item in everything} == {
        TICKET.skill_id,
        INVOICE.skill_id,
        DEPLOY.skill_id,
    }
    assert all(item.score == 0 for item in everything)
    assert await retriever.retrieve("ticket", limit=5, filters={"tag": "billing"}) == []
    assert len(await retriever.retrieve("", limit=1)) == 1
    with pytest.raises(SkillDiscoveryError):
        await retriever.retrieve("x", limit=0)


async def test_semantic_retrieval_ranks_by_cosine_similarity() -> None:
    retriever = SemanticSkillRetriever(KeywordEmbedder())
    await retriever.index(CATALOG)
    results = await retriever.retrieve("invoice invoice", limit=3)
    assert results[0].skill == INVOICE
    assert results[0].score == pytest.approx(1.0)
    filtered = await retriever.retrieve("invoice", limit=3, filters={"name": "deploy-service"})
    assert [item.skill for item in filtered] == [DEPLOY]
    zero = await retriever.retrieve("nothing relevant", limit=3)
    assert all(item.score == 0 for item in zero)


class BrokenEmbedder(KeywordEmbedder):
    def __init__(self, *, documents: bool = False, query: bool = False, count: bool = False):
        super().__init__()
        self.fail_documents = documents
        self.fail_query = query
        self.wrong_count = count
        self.dimension = 3

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail_documents:
            raise RuntimeError("down")
        vectors = await super().embed_documents(texts)
        return vectors[:-1] if self.wrong_count else vectors

    async def embed_query(self, text: str) -> list[float]:
        if self.fail_query:
            raise RuntimeError("down")
        return [1.0] * (self.dimension + 1)


async def test_semantic_retrieval_wraps_embedder_failures() -> None:
    with pytest.raises(SkillDiscoveryError, match="index embedding"):
        await SemanticSkillRetriever(BrokenEmbedder(documents=True)).index(CATALOG)
    with pytest.raises(SkillDiscoveryError, match="different number"):
        await SemanticSkillRetriever(BrokenEmbedder(count=True)).index(CATALOG)
    retriever = SemanticSkillRetriever(BrokenEmbedder(query=True))
    with pytest.raises(SkillDiscoveryError, match="query embedding"):
        await retriever.retrieve("x", limit=1)
    retriever = SemanticSkillRetriever(BrokenEmbedder())
    await retriever.index(CATALOG)
    with pytest.raises(SkillDiscoveryError, match="dimension"):
        await retriever.retrieve("x", limit=1)
    with pytest.raises(SkillDiscoveryError):
        await retriever.retrieve("x", limit=0)


async def test_score_reranker_orders_and_truncates() -> None:
    candidates = [RetrievedSkill(INVOICE, 1.0), RetrievedSkill(TICKET, 3.0)]
    assert await ScoreSkillReranker().rerank("q", candidates, top_k=1) == [TICKET]


async def test_pipeline_defaults_to_lexical() -> None:
    provider = PipelineDiscoveryProvider()
    await provider.index(CATALOG)
    assert await provider.discover("explain invoice", top_k=1) == [INVOICE]
    assert await provider.discover("explain", filters={"tag": "support"}) == []
    with pytest.raises(SkillDiscoveryError, match="top_k"):
        await provider.discover("x", top_k=0)
    with pytest.raises(SkillDiscoveryError, match="unsupported"):
        await provider.discover("x", filters={"owner": "me"})
    with pytest.raises(ValueError, match="candidate_pool_size"):
        PipelineDiscoveryProvider(candidate_pool_size=0)


class ScriptedRetriever(SkillRetriever):
    def __init__(self, results: list[RetrievedSkill]) -> None:
        self.results = results
        self.limits: list[int] = []

    async def index(self, skills: Sequence[Skill]) -> None:
        del skills

    async def retrieve(
        self, query: str, *, limit: int, filters: Mapping[str, Any] | None = None
    ) -> list[RetrievedSkill]:
        self.limits.append(limit)
        return self.results


class ScriptedReranker(SkillReranker):
    def __init__(self, result: list[Skill]) -> None:
        self.result = result

    async def rerank(
        self, query: str, candidates: Sequence[RetrievedSkill], *, top_k: int
    ) -> list[Skill]:
        return self.result


async def test_pipeline_requests_the_candidate_pool_and_drops_invalid_candidates() -> None:
    retriever = ScriptedRetriever([RetrievedSkill(PENDING, 9.0), RetrievedSkill(TICKET, 1.0)])
    provider = PipelineDiscoveryProvider(retriever, candidate_pool_size=7)
    assert await provider.discover("ticket", top_k=3) == [TICKET]
    assert retriever.limits == [7]


@pytest.mark.parametrize(
    ("retrieved", "ranked", "message"),
    [
        ([RetrievedSkill(TICKET, 1.0)] * 3, [], "candidate limit"),
        ([RetrievedSkill(TICKET, 1.0)], [TICKET, INVOICE, DEPLOY], "more than top_k"),
        ([RetrievedSkill(TICKET, 1.0)], [INVOICE], "invalid candidate"),
        ([RetrievedSkill(TICKET, 1.0)], [TICKET, TICKET], "invalid candidate"),
    ],
)
async def test_pipeline_verifies_each_stage(
    retrieved: list[RetrievedSkill], ranked: list[Skill], message: str
) -> None:
    provider = PipelineDiscoveryProvider(
        ScriptedRetriever(retrieved), reranker=ScriptedReranker(ranked), candidate_pool_size=2
    )
    with pytest.raises(SkillDiscoveryError, match=message):
        await provider.discover("q", top_k=2)
