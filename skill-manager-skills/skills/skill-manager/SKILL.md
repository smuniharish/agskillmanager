---
name: skill-manager
description: >-
  Use when integrating or debugging the skill-manager Python package: register
  YAML Skills, discover instructions, compose dependency bundles, generate
  revisions, require human approval, reject and regenerate from feedback,
  resolve MCP capabilities, refresh catalogs, configure PostgreSQL or export
  OpenTelemetry and agxai decisions. Works with plain Python, LangGraph,
  LangChain, Agno, CrewAI and deepagents. For implementing a new source,
  registry, generator, validator, embedder or sink use skill-manager-extend.
license: Apache-2.0
compatibility: Python 3.12+ with skill-manager 1.x. Optional integrations require their extras.
metadata:
  version: "1.0.0"
  documentation: "https://skill-manager.readthedocs.io/en/latest/"
---

# Use Skill Manager

Skill Manager owns validated instruction data and lifecycle, not agent execution.

## Workflow

1. Inspect the installed package, current constructor, Skill documents and
   bundle-consumption boundary. Run [verify_setup.py](./scripts/verify_setup.py).
2. Choose sources and registry. Default memory storage is not restart-safe.
   Configure durable registry plus durable feedback storage for review queues.
3. Construct `SkillManager` with fully built collaborators. Preserve their
   downstream configuration; do not rebuild stores, clients or policies inside a wrapper.
4. Register human Skills with `await manager.register_skill(skill)`. Discover
   with `await manager.discover(query, top_k=...)`; only active revisions qualify.
5. Compose `await manager.build_bundle(matches)` and hand its instructions and
   capability data to the application's agent. Do not execute Skills here.
6. Generate using a `SkillGenerator` instance, not a raw framework runnable.
   For LangChain use `XStructuredSkillGenerator(runnable, **options)`.
7. Enable `require_human_approval=True` for untrusted generation. Approve/reject
   pending immutable IDs; regenerate rejected Skills with `parent_skill_id=...`.
   Feedback never grants approval by itself.
8. Use `async with SkillManager(...)`; close caller-owned collaborators separately.
9. Run a focused example/test and inspect `source_errors` and `observability_errors`.

## Read as needed

- [Architecture](./references/architecture.md): boundaries and ownership.
- [Configuration](./references/configuration.md): policy, persistence and limits.
- [Integration](./references/integration.md): frameworks and downstream options.
- [Troubleshooting](./references/troubleshooting.md): common failure paths.
- [Quickstart template](./assets/quickstart.py): executable offline example.
- [Evaluation prompts](./evals/evals.json): representative tasks and assertions.

Never put credentials in Skills, feedback or logs. Never overwrite instruction
content under an existing Skill ID. Do not bypass approval with `model_copy`.
