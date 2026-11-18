from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from retrievalloom import (
    Components,
    DeleteReport,
    DocumentInput,
    IngestReport,
    RetrievalEngine,
    RetrievalResult,
    Scope,
    SourceDescriptor,
    TextRepresentation,
)

from skill_manager import (
    DEFAULT_SCOPE,
    DiscoveryProvider,
    RetrievalLoomDiscoveryProvider,
    Skill,
    SkillDiscoveryError,
    SkillLifecycleState,
    SkillManager,
    matches_filters,
    skill_document,
    validate_filters,
)
from tests.helpers import KeywordEmbeddingModel, make_skill

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


def test_constructor_validation() -> None:
    with pytest.raises(ValueError, match="candidate_pool_size"):
        RetrievalLoomDiscoveryProvider(candidate_pool_size=0)
    with pytest.raises(ValueError, match="either engine"):
        RetrievalLoomDiscoveryProvider(RetrievalEngine(), components=Components())


async def test_hybrid_discovery_ranks_filters_and_tolerates_typos() -> None:
    provider = RetrievalLoomDiscoveryProvider()
    assert provider.scope == DEFAULT_SCOPE
    await provider.index(CATALOG)
    assert await provider.discover("explain invoice", top_k=1) == [INVOICE]
    assert await provider.discover("suport tickt") == [TICKET]
    assert PENDING not in await provider.discover("draft ticket", top_k=10)
    assert await provider.discover("ticket", filters={"tag": "billing"}) == []
    assert await provider.discover("ticket", filters={"capability": "tickets.read"}) == [TICKET]
    assert await provider.discover(
        "deploy", filters={"name": "deploy-service", "version": "2.0.0"}
    ) == [DEPLOY]
    assert await provider.discover("nothing-relevant-zzz") == []
    await provider.aclose()


async def test_empty_query_lists_active_filtered_skills() -> None:
    provider = RetrievalLoomDiscoveryProvider()
    await provider.index(CATALOG)
    expected = sorted((TICKET, INVOICE, DEPLOY), key=lambda skill: skill.skill_id)
    assert await provider.discover("  ", top_k=10) == expected
    assert await provider.discover("", top_k=1) == expected[:1]
    assert await provider.discover("", filters={"tag": "billing"}) == [INVOICE]


async def test_argument_validation() -> None:
    provider = RetrievalLoomDiscoveryProvider()
    with pytest.raises(SkillDiscoveryError, match="top_k"):
        await provider.discover("x", top_k=0)
    with pytest.raises(SkillDiscoveryError, match="unsupported"):
        await provider.discover("x", filters={"owner": "me"})


class CountingEngine(RetrievalEngine):
    def __init__(self) -> None:
        super().__init__()
        self.ingested: list[list[str]] = []
        self.deleted: list[list[str]] = []

    async def ingest(self, documents: Sequence[DocumentInput], **values: Any) -> IngestReport:
        self.ingested.append([document.id for document in documents])
        return await super().ingest(documents, **values)

    async def delete(self, document_ids: Sequence[str], **values: Any) -> DeleteReport:
        self.deleted.append(list(document_ids))
        return await super().delete(document_ids, **values)


async def test_reindex_ingests_only_changes_and_deletes_removed_skills() -> None:
    engine = CountingEngine()
    provider = RetrievalLoomDiscoveryProvider(engine)
    await provider.index(CATALOG)
    assert engine.ingested == [[TICKET.skill_id, INVOICE.skill_id, DEPLOY.skill_id]]
    await provider.index(CATALOG)
    assert len(engine.ingested) == 1
    renamed = TICKET.model_copy(
        update={"metadata": TICKET.metadata.model_copy(update={"description": "Triage alerts."})}
    )
    await provider.index((renamed, DEPLOY))
    assert engine.ingested[-1] == [renamed.skill_id]
    assert engine.deleted == [[INVOICE.skill_id]]
    assert await provider.discover("invoice") == []
    assert await provider.discover("triage alerts") == [renamed]
    await provider.aclose()
    assert engine.state.value != "closed"
    await engine.close()


async def test_results_are_checked_against_the_indexed_catalog() -> None:
    engine = RetrievalEngine()
    scope = Scope(tenant_id="shared", collection="skills")
    provider = RetrievalLoomDiscoveryProvider(engine, scope=scope)
    await provider.index((TICKET,))
    stale = DocumentInput(
        id=TICKET.skill_id,
        source=SourceDescriptor(uri="skill://stale"),
        metadata={"tags": ["billing"]},
        representations=[TextRepresentation(text="ticket billing")],
    )
    stranger = DocumentInput(
        id="stranger",
        source=SourceDescriptor(uri="kb://stranger"),
        representations=[TextRepresentation(text="ticket stranger")],
    )
    await engine.ingest([stale, stranger], scope=scope)
    assert await provider.discover("ticket", filters={"tag": "billing"}) == []
    assert await provider.discover("ticket", top_k=5) == [TICKET]
    await engine.close()


async def test_semantic_search_uses_the_configured_embedding_model() -> None:
    provider = RetrievalLoomDiscoveryProvider(
        components=Components(embedding=KeywordEmbeddingModel())
    )
    await provider.index(CATALOG)
    assert (await provider.discover("invoice invoice", top_k=1)) == [INVOICE]
    await provider.aclose()
    assert provider.engine.state.value == "closed"


class FailingEngine(RetrievalEngine):
    def __init__(self, fail: str) -> None:
        super().__init__()
        self.fail = fail

    async def initialize(self) -> None:
        if self.fail == "initialize":
            raise RuntimeError("down")
        await super().initialize()

    async def ingest(self, documents: Sequence[DocumentInput], **values: Any) -> IngestReport:
        if self.fail == "ingest":
            raise RuntimeError("down")
        report = await super().ingest(documents, **values)
        if self.fail == "rejected":
            item = report.documents[0]
            rejected = item.model_copy(update={"outcome": type(item.outcome)("rejected")})
            return report.model_copy(update={"documents": (rejected, *report.documents[1:])})
        return report

    async def retrieve(self, query: str, **values: Any) -> RetrievalResult:
        if self.fail == "retrieve":
            raise RuntimeError("down")
        return await super().retrieve(query, **values)


@pytest.mark.parametrize(
    ("fail", "message"),
    [
        ("initialize", "initialize"),
        ("ingest", "could not index"),
        ("rejected", "did not index every Skill"),
    ],
)
async def test_index_failures_raise_discovery_errors(fail: str, message: str) -> None:
    provider = RetrievalLoomDiscoveryProvider(FailingEngine(fail))
    with pytest.raises(SkillDiscoveryError, match=message):
        await provider.index(CATALOG)


async def test_initialize_failure_also_surfaces_from_discover() -> None:
    provider = RetrievalLoomDiscoveryProvider(FailingEngine("initialize"))
    with pytest.raises(SkillDiscoveryError, match="initialize"):
        await provider.discover("ticket")


async def test_retrieval_failure_raises_discovery_error() -> None:
    provider = RetrievalLoomDiscoveryProvider(FailingEngine("retrieve"))
    await provider.index(CATALOG)
    with pytest.raises(SkillDiscoveryError, match="retrieval failed"):
        await provider.discover("ticket")


async def test_manager_closes_only_its_own_provider() -> None:
    injected = RetrievalLoomDiscoveryProvider()
    async with SkillManager(discovery=injected) as manager:
        await manager.register_skill(INVOICE)
        assert await manager.discover("invoice") == [INVOICE]
    assert injected.engine.state.value != "closed"
    await injected.aclose()


async def test_discovery_provider_default_aclose_is_a_no_op() -> None:
    class Static(DiscoveryProvider):
        async def index(self, skills: Sequence[Skill]) -> None:
            del skills

        async def discover(
            self, query: str, *, top_k: int = 5, filters: Mapping[str, Any] | None = None
        ) -> list[Skill]:
            return []

    await Static().aclose()
