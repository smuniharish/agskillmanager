# AG Skill Manager

<img src="assets/logo.svg" alt="AG Skill Manager" width="72">

**Govern reusable instructions without choosing an agent framework.**

Skill Manager validates and stores Skills, discovers the right revisions, enforces
human review, resolves dependencies and MCP capabilities, and produces a typed
`SkillBundle`. Your application owns execution.

| Start here | What you will learn |
|---|---|
| [Quickstart](getting-started/quickstart.md) | Register, discover and compose Skills |
| [Governance](guide/governance.md) | Generate, reject, improve and approve |
| [Customization](integrations/customization.md) | Preserve downstream options |
| [Examples](examples/index.md) | Frameworks, PostgreSQL, MCP and OTel |
| [API reference](api/manager.md) | Public signatures and contracts |

Core installation has no LangChain or LangGraph dependency. Every application
extension point is an asynchronous ABC; optional integrations live in extras.
