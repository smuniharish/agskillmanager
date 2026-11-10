# Skill validation

```console
uv run --no-sync agentskills validate agskillmanager-skills/skills/agskillmanager
uv run --no-sync agentskills validate agskillmanager-skills/skills/agskillmanager-extend
uv run --no-sync pytest tests/skill
uv run --no-sync python agskillmanager-skills/skills/agskillmanager/scripts/verify_setup.py
uv run --no-sync python agskillmanager-skills/skills/agskillmanager-extend/scripts/check_source.py source_template:MemorySkillSource --path agskillmanager-skills/skills/agskillmanager-extend/assets
```

Evaluation JSON files describe behavioral tasks and expected outcomes for agent
evaluation. Structural validation and executable scripts are tested automatically;
prompt adherence still requires running those tasks in the target agent.
