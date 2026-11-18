# Agent Skills

Portable skills teach coding agents to use and extend the package:

- **agskillmanager:** integration, governance, discovery, storage and telemetry.
- **agskillmanager-extend:** async sources, registries, generators and contract tests.

```console
npx skills add smuniharish/agskillmanager --skill agskillmanager
npx skills add smuniharish/agskillmanager --skill agskillmanager-extend
```

For manual installation, copy a skill folder from
[agskillmanager-skills/skills](https://github.com/smuniharish/agskillmanager/tree/master/agskillmanager-skills/skills)
into your agent's workspace skills directory. Keep bundled references, scripts,
assets and evals together.

The package's `Skill` domain model and these coding-agent skills are separate:
Agent Skills guide development; application Skills supply governed runtime instructions.

Validate frontmatter with skills-ref and execute the setup/contract scripts.
Evaluation JSON contains representative tasks and expected outcomes, not a claim
that every agent has passed them. See
[validation instructions](https://github.com/smuniharish/agskillmanager/blob/master/agskillmanager-skills/validation/README.md).

## Skills from dependency packages

Each runtime dependency publishes its own Agent Skills through a `skills.sh.json`
manifest. Install them when an agent works directly with that package; the
agskillmanager skills cover only how this package uses them.

| Package | Skills | Install |
| --- | --- | --- |
| [retrievalloom](https://github.com/smuniharish/retrievalloom) | `retrievalloom`, `retrievalloom-extend` | `npx skills add smuniharish/retrievalloom` |
| [agxai](https://github.com/smuniharish/agxai) | `agxai`, `agxai-extend` | `npx skills add smuniharish/agxai` |
| [feedback-manager](https://github.com/smuniharish/feedback-manager) | `feedback-manager`, `feedback-manager-extend`, `feedback-manager-learning` | `npx skills add smuniharish/feedback-manager` |
| [mcp-capability-router](https://github.com/smuniharish/mcp-capabilty-router) | `mcp-capability-router`, `mcp-capability-router-extend` | `npx skills add smuniharish/mcp-capabilty-router` |
| [refresh-engine](https://github.com/smuniharish/refresh-engine) | `refresh-engine`, `refresh-engine-extend` | `npx skills add smuniharish/refresh-engine` |
| [xstructured](https://github.com/smuniharish/xstructured) (`langchain` extra) | `xstructured`, `xstructured-extend` | `npx skills add smuniharish/xstructured` |

Add `--skill <name>` to install a single skill. This table lists only skills
published by the first-party dependencies listed above.
