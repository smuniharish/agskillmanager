# Changelog

## 2.0.0

Skill discovery now runs on [RetrievalLoom](https://pypi.org/project/retrievalloom/).

- Added `RetrievalLoomDiscoveryProvider`, the new default `SkillManager` discovery
  provider: keyword, typo-tolerant fuzzy and BM25 search out of the box, with optional
  dense embeddings, reranking, NLI and durable stores through RetrievalLoom `Components`.
  Filters run inside the engine; re-indexing only ingests changed Skills.
- Added `DiscoveryProvider.aclose()`; `SkillManager.aclose()` closes the default
  provider it creates.
- Added `skill_manager.integrations.langchain.LangChainEmbeddingModel`.
- Added `examples/local_models_discovery.py` (bge-m3, bge-reranker-v2-m3, NLI) and the
  `models` dependency group (sentence-transformers 6.3+, transformers 5.23+).
- Raised minimum versions to the latest compatible releases (agxai 1.0.3,
  mcp-capability-router 1.0.2, refresh-engine 1.0.1; `langchain` extra:
  langchain-core 1.8.2, xstructured 1.0.1; `postgres` extra: psycopg 3.3.9).
- Documentation: Mermaid architecture diagram and a list of Agent Skills published
  by the first-party dependencies.

### Breaking changes

- Removed `SkillRetriever`, `SkillReranker`, `RetrievedSkill`, `LexicalSkillRetriever`,
  `SemanticSkillRetriever`, `ScoreSkillReranker` and `PipelineDiscoveryProvider`.
  Use `RetrievalLoomDiscoveryProvider`; pass custom models as RetrievalLoom
  `EmbeddingModelABC`/`RerankerABC` components.
- Removed `skill_manager.integrations.langchain.LangChainEmbedder`; use
  `LangChainEmbeddingModel(embeddings, dimensions=...)`.
- `retrievalloom` is a core dependency, and it supports Python 3.12–3.14, so
  Python 3.15 is no longer supported.
- Initial indexing is slower than the 1.x in-memory lexical index (about 104 s for
  10,000 Skills in the benchmark), because ingestion is durable and idempotent. Index
  once at startup; later re-indexing ingests only changes. See `docs/benchmarks.md`.

| 1.x | 2.0 |
|---|---|
| `PipelineDiscoveryProvider()` | `RetrievalLoomDiscoveryProvider()` |
| `PipelineDiscoveryProvider(SemanticSkillRetriever(embedder))` | `RetrievalLoomDiscoveryProvider(components=Components(embedding=model))` |
| `PipelineDiscoveryProvider(retriever, reranker=reranker)` | `RetrievalLoomDiscoveryProvider(components=Components(embedding=..., reranker=...))` |
| `LangChainEmbedder(embeddings)` | `LangChainEmbeddingModel(embeddings, dimensions=n)` |

## 1.0.0

- Framework-agnostic async Skill lifecycle and ABC extension points.
- Governed generation, approval, rejection, revision lineage and feedback.
- Deterministic dependency bundles and bounded discovery/capability resolution.
- Injectable feedback, MCP, refresh and agxai runtimes.
- Optional LangChain/xstructured, PostgreSQL and OpenTelemetry integrations.
- Contract suites, typed distribution, Python 3.12–3.15 CI.
- Zensical documentation, executable examples and portable Agent Skills.
