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
