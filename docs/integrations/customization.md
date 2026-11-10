# Downstream customization

Inject fully built collaborators instead of copying their configuration into a
wrapper. Your stores, policies, plugins and pools remain the same objects.
Injected collaborators remain caller-owned.

## Runtime packages

| Package | Integration | Customizable downstream surfaces |
|---|---|---|
| feedback-manager | `feedback_manager=FeedbackManager(...)` | Store, router, correlator, provenance, lifecycle/redaction/failure policies, observability, learning engine/job store/scope/change source |
| mcp-capability-router | `mcp_runtime=MCPRuntime(...)` | Registry/retriever, concurrency, resilience, interceptors, metrics, state-store factory; transport/auth/client options through server registration |
| refresh-engine | `refresh_engine=RefreshEngine(...)` | Resource source, operation, fingerprint, store, config and events |
| agxai | `xai_runtime=XAIRuntime(...)` | Config, registry of storage/observability/explanation/attribution/policy collaborators, plugins, state capture and tenant/application/graph identity |
| xstructured (`langchain`) | `XStructuredSkillGenerator(runnable, repair=..., **options)` | Runnable, repair, parser/repair configs, renderers, extractors, recovery, decoder and observer options accepted by xstructured |
| LangChain Core (`langchain`) | `LangChainEmbedder(embeddings)`; generator runnable | Any embeddings/runnable implementation and its provider-specific configuration |
| psycopg (`postgres`) | PostgreSQL source/registry with prebuilt pool | Connection/auth/TLS, sizing, timeouts, table/source identity, pool ownership |
| OpenTelemetry (`otel`) | Sink with tracer/meter or providers | Sampling, processors/readers/exporters/resources, instrumentation name, ownership |

Pydantic, PyYAML and packaging supply data validation, safe serialization and
version constraints, not application runtimes needing a second store/policy facade.

## Package-owned seams

Async ABCs: `SkillSource`, `SkillRegistry`, `SkillValidator`, `SkillGenerator`,
`DiscoveryProvider`, `SkillRetriever`, `SkillReranker`, `SkillObservabilitySink`.
Semantic retrieval reuses the downstream `Embedder` ABC.

```python
from feedback_manager import FeedbackManager
from skill_manager import SkillManager


async def use_custom_feedback(store):
    feedback = FeedbackManager(store=store, learning=False)
    try:
        async with SkillManager(feedback_manager=feedback) as manager:
            return await manager.list_pending_skills()
    finally:
        await feedback.aclose()
```

Configure learning artifact/vector/graph storage through feedback-manager's
learning engine, then inject that manager. For external scheduling call `refresh`
from your chosen scheduler. No downstream configuration is reconstructed.

See the runnable [customization matrix](https://github.com/smuniharish/skill-manager/blob/master/examples/customization_matrix.py).
