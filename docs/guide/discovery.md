# Discovery and dependencies

`RetrievalLoomDiscoveryProvider` is the default discovery provider. It indexes
each active Skill as one [RetrievalLoom](https://retrievalloom.readthedocs.io/)
document (ID = Skill ID, text = `skill_document(skill)`) and runs RetrievalLoom's
keyword, typo-tolerant fuzzy and BM25 search in memory, with no model download
or network access. Re-indexing ingests only new or changed Skills and deletes
Skills that are no longer active.

Exact filters `name`, `version`, `tag` and `capability` are stored as document
metadata and applied inside the engine; every result is checked again against the
indexed catalog, so inactive, filtered-out or unknown documents are never returned.
Unknown filters raise `SkillDiscoveryError`. Empty queries return the active,
filtered Skills ordered by Skill ID. `candidate_pool_size` sets the minimum number
of engine results requested before trimming to `top_k`.

## Semantic search, reranking and persistence

Pass RetrievalLoom `Components` (or a configured `RetrievalEngine`) to add dense
semantic search, a cross-encoder reranker, NLI, or durable SQLite/PostgreSQL
metadata and Qdrant vectors:

```python
from retrievalloom import Components
from skill_manager import RetrievalLoomDiscoveryProvider, SkillManager

discovery = RetrievalLoomDiscoveryProvider(
    components=Components(embedding=my_embedding_model, reranker=my_reranker)
)
async with SkillManager(discovery=discovery) as manager:
    matches = await manager.discover("get my money back", top_k=3)
await discovery.aclose()
```

Implement `retrievalloom.contracts.models.EmbeddingModelABC`, `RerankerABC` or
`NLIABC` for your own models; with the `langchain` extra,
`skill_manager.integrations.langchain.LangChainEmbeddingModel` adapts any
LangChain ``Embeddings``. `examples/local_models_discovery.py` wires local bge-m3,
bge-reranker-v2-m3 and NLI models. Engine, ingestion and retrieval failures are
raised as `SkillDiscoveryError`.

A provider that creates its engine closes it in `aclose`; an injected `engine`
stays open for its owner. `SkillManager` closes the default provider it creates and
leaves an injected provider open. Use `scope=Scope(...)` to keep Skills in their
own tenant and collection when sharing an engine.

Implement `DiscoveryProvider` to replace RetrievalLoom entirely.

## Dependencies

Requirements use PEP 440 constraints such as `>=1,<2`, or `*`. Resolution prefers
the highest matching active version and backtracks when another branch constrains
it. One revision is selected per name. Cycles report their path; missing or
conflicting requirements raise errors. Bundle order is deterministic,
dependencies before dependents.

## MCP capabilities

Inject a fully configured `MCPRuntime`. Requirements match exact names or IDs;
the lowest capability ID breaks ties. Results use a bounded LRU invalidated by
refresh. Transport, execution and access controls belong to the runtime and application.
