# Skill validation

```console
uv run --no-sync agentskills validate skill-manager-skills/skills/skill-manager
uv run --no-sync agentskills validate skill-manager-skills/skills/skill-manager-extend
uv run --no-sync pytest tests/skill
uv run --no-sync python skill-manager-skills/skills/skill-manager/scripts/verify_setup.py
uv run --no-sync python skill-manager-skills/skills/skill-manager-extend/scripts/check_source.py source_template:MemorySkillSource --path skill-manager-skills/skills/skill-manager-extend/assets
```

Evaluation JSON files describe behavioral tasks and expected outcomes for agent
evaluation. Structural validation and executable scripts are tested automatically;
prompt adherence still requires running those tasks in the target agent.
