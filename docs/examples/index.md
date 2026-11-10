# Examples

```console
uv sync --locked --all-extras --all-groups
uv run --no-sync python examples/quickstart.py
uv run --no-sync pytest tests/examples -m "not live"
```

Sources: [examples/](https://github.com/smuniharish/agskillmanager/tree/master/examples).

## Offline workflows

| Script | Demonstrates |
|---|---|
| `quickstart.py` | Registration, discovery and dependency bundles |
| `filesystem_source.py` | Multiple sources and reload |
| `approval_workflow.py` | Rejection, regeneration, approval and lineage |
| `semantic_discovery.py` | Custom async embedder and reranker |
| `langchain_embeddings.py` | LangChain adapter with local embeddings |
| `custom_framework.py` | Framework-free prompt handoff |
| `refresh.py` | External resource refresh and scheduling |
| `xai_decisions.py` | Collect and explain decisions |
| `customization_matrix.py` | Every constructor collaborator |
| `streamlit_catalog.py` | Register, generate, reject, regenerate and approve in a local UI |

The UI's synchronous entry point is a necessary Streamlit boundary. A serialized
async runner retains the review queue and feedback across reruns. This is a local
demo, not an authenticated or durable multi-user review service; review state
uses memory and approved YAML uses the configured directory.

## Model-backed examples

`llm_skill_generation.py`, `langgraph_agent.py`, `create_agent.py` and
`deepagents_agent.py` read `EXPLABS_API_KEY` or `OPENAI_API_KEY`.
`OPENAI_BASE_URL` and `OPENAI_MODEL` select any OpenAI-compatible endpoint.
Never commit a populated `.env`; export settings into the shell before running.
Tests execute all four with scripted chat models; live tests run when a key is present.

## Service-backed examples

Start local containers using Podman Desktop:

```console
podman run -d --name agskillmanager-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=skill_manager -p 127.0.0.1:55432:5432 postgres:18-alpine
podman run -d --name agskillmanager-lgtm -p 127.0.0.1:14318:4318 -p 127.0.0.1:13000:3000 -p 127.0.0.1:13200:3200 -p 127.0.0.1:19090:9090 grafana/otel-lgtm
uv run --no-sync python examples/local_mcp_server.py
```

The database password is for an isolated local test container only.
In another shell set:

| Variable | Local value | Example |
|---|---|---|
| `SKILL_MANAGER_POSTGRES_DSN` | `postgresql://postgres:postgres@127.0.0.1:55432/skill_manager` | `postgres_catalog.py` |
| `SKILL_MANAGER_TEST_POSTGRES_DSN` | Same DSN | PostgreSQL contracts |
| `SKILL_MANAGER_MCP_URL` | `http://127.0.0.1:8765/mcp` | `mcp_capabilities.py` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:14318` | `otel_observability.py` |
| `SKILL_MANAGER_UI_SKILLS_DIR` | Application-owned directory | `streamlit_catalog.py` |

```console
uv run --no-sync pytest tests/examples -m live
uv run --no-sync streamlit run examples/streamlit_catalog.py
```

Check actual ingestion in Tempo/Prometheus, not just exporter exit codes.
Stop the server and named containers when finished.
