<p align="center">
  <img src="https://raw.githubusercontent.com/smuniharish/skill-manager/master/docs/assets/logo.svg" width="80" alt="skill-manager">
</p>

# skill-manager

**Governed, framework-agnostic Skill lifecycle management for AI agents.**

[![CI](https://github.com/smuniharish/skill-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/smuniharish/skill-manager/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/skill-manager)](https://pypi.org/project/skill-manager/)
[![Documentation](https://readthedocs.org/projects/skill-manager/badge/?version=latest)](https://skill-manager.readthedocs.io/en/latest/)
[![Python](https://img.shields.io/pypi/pyversions/skill-manager)](https://pypi.org/project/skill-manager/)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/smuniharish/skill-manager/actions/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/typing-typed-blue)](https://github.com/smuniharish/skill-manager/blob/master/src/skill_manager/py.typed)
[![License](https://img.shields.io/github/license/smuniharish/skill-manager)](https://github.com/smuniharish/skill-manager/blob/master/LICENSE)

Reusable instructions become application assets: validated, discoverable, versioned,
reviewable and ready to compose. Skill Manager produces a typed `SkillBundle`;
your agent framework owns execution.

## Why Skill Manager?

- Canonical YAML and typed, validated domain models.
- Immutable revision identity, dependency resolution and provenance lineage.
- Async ABC extension points for storage, discovery, generation and telemetry.
- Human approval, rejection and feedback-informed regeneration.
- MCP capability resolution, refresh scheduling and bounded caches.
- Fully configured downstream runtimes stay injectable, including their stores,
  policies, plugins and transport options.
- No LangChain or LangGraph dependency in core. Works with plain Python, Agno,
  CrewAI or any runtime that consumes instructions.

## Install

Python 3.12 through 3.15.

```console
pip install skill-manager
pip install "skill-manager[langchain]"     # xstructured generation and embeddings
pip install "skill-manager[postgres,otel]" # PostgreSQL and OpenTelemetry
pip install "skill-manager[all]"
```

## Quickstart

```python
import asyncio

from skill_manager import Skill, SkillManager, SkillMetadata


async def main() -> None:
    async with SkillManager() as manager:
        skill = await manager.register_skill(
            Skill(
                metadata=SkillMetadata(
                    name="incident-review",
                    version="1.0.0",
                    description="Review incidents using verified evidence.",
                ),
                instructions=(
                    "Separate confirmed facts from hypotheses.",
                    "Report unresolved risks explicitly.",
                ),
            )
        )
        matches = await manager.discover("review incident", top_k=1)
        bundle = await manager.build_bundle(matches)
        print(skill.skill_id)
        print("\n".join(bundle.instructions))


asyncio.run(main())
```

Add a `FilesystemSkillSource` for YAML persistence, or inject a PostgreSQL registry
for a shared catalog. Enable `require_human_approval=True` when generating untrusted
instructions. Restart-safe review needs durable registry and feedback storage.

## Customize without losing downstream options

| Runtime | Inject through | Configure in that runtime |
|---|---|---|
| feedback-manager | `feedback_manager=` | Storage, routing, policies and learning |
| mcp-capability-router | `mcp_runtime=` | Registry, retrieval, transport, auth, resilience |
| refresh-engine | `refresh_engine=` | Source, operation, fingerprint, storage and events |
| agxai | `xai_runtime=` | Provenance, disclosure, explanation and plugins |
| xstructured | `XStructuredSkillGenerator(...)` | Runnable, repair and structured-output options |

Caller-created collaborators remain caller-owned. See the full
[customization matrix](https://skill-manager.readthedocs.io/en/latest/integrations/customization/).

## Explore

- [Documentation](https://skill-manager.readthedocs.io/en/latest/)
- [Runnable examples](https://github.com/smuniharish/skill-manager/tree/master/examples):
  plain Python, LangGraph, LangChain, deepagents, approval, PostgreSQL, MCP and OTel.
- [API reference](https://skill-manager.readthedocs.io/en/latest/api/manager/)
- [Agent Skills](https://github.com/smuniharish/skill-manager/tree/master/skill-manager-skills)
- [Contributing](https://github.com/smuniharish/skill-manager/blob/master/CONTRIBUTING.md)
- [Security](https://github.com/smuniharish/skill-manager/blob/master/SECURITY.md)
- [Changelog](https://github.com/smuniharish/skill-manager/blob/master/CHANGELOG.md)

## Development

```console
uv sync --locked --all-extras --all-groups
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyrefly check
uv run --no-sync pytest
uv run --no-sync zensical build --strict
```

CI measures 100% line and branch coverage with a PostgreSQL service, checks Python
3.12–3.15, validates docs and verifies a core wheel without optional frameworks.
Service/model examples are live-tested when their documented environment variables
are set. Never commit credentials.

Licensed under [Apache-2.0](https://github.com/smuniharish/skill-manager/blob/master/LICENSE).
