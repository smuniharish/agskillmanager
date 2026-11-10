# Troubleshooting

| Symptom | Check |
|---|---|
| Missing discovery result | Only active revisions are searchable; inspect pending Skills and filters |
| Missing Skill with `SkillSourceError` | Inspect `source_errors`; an unreadable source may contain it |
| Agent becomes pending on reload | Reuse the durable feedback store containing resolved approval |
| Capability cannot resolve | Configure `MCPRuntime`, refresh servers, use exact names or IDs |
| Import requests an extra | Install the extra named by `OptionalDependencyError` |
| PostgreSQL fails on Windows | Run psycopg on `asyncio.SelectorEventLoop` |
| Active revision conflict | Use a new version or explicitly resolve the existing revision |
| Telemetry missing | Inspect `observability_errors`, exporters and collector readiness |
| Metadata rejected | Remove credentials and credential-like keys |

Do not catch and ignore package exceptions. Report enough sanitized context to
identify the operation without logging Skills containing private data.
