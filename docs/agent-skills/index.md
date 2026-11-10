# Agent Skills

Portable skills teach coding agents to use and extend the package:

- **skill-manager:** integration, governance, discovery, storage and telemetry.
- **skill-manager-extend:** async sources, registries, generators and contract tests.

```console
npx skills add smuniharish/skill-manager --skill skill-manager
npx skills add smuniharish/skill-manager --skill skill-manager-extend
```

For manual installation, copy a skill folder from
[skill-manager-skills/skills](https://github.com/smuniharish/skill-manager/tree/master/skill-manager-skills/skills)
into your agent's workspace skills directory. Keep bundled references, scripts,
assets and evals together.

The package's `Skill` domain model and these coding-agent skills are separate:
Agent Skills guide development; application Skills supply governed runtime instructions.

Validate frontmatter with skills-ref and execute the setup/contract scripts.
Evaluation JSON contains representative tasks and expected outcomes, not a claim
that every agent has passed them. See
[validation instructions](https://github.com/smuniharish/skill-manager/blob/master/skill-manager-skills/validation/README.md).
