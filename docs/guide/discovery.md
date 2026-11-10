# Discovery and dependencies

`PipelineDiscoveryProvider` combines retrieval and reranking. Default lexical
retrieval precomputes search tokens and ranks matched terms. Empty queries return
bounded active candidates. Exact filters: `name`, `version`, `tag`, `capability`.
Unknown filters raise `SkillDiscoveryError`.

For semantic search inject `SemanticSkillRetriever(embedder)` using the downstream
`mcp_capability_router.Embedder` ABC. Document and query dimensions must match;
vectors are normalized, and zero vectors have zero similarity. Embedding failures
are surfaced, never silently replaced with lexical results.

`SkillRetriever` and `SkillReranker` are async ABCs. The pipeline enforces candidate
and output limits and refuses invented, altered or duplicated reranker results.
`candidate_pool_size` controls recall before reranking; `top_k` bounds the final result.

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
