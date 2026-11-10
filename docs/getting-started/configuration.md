# Configuration

`SkillManagerConfig` is immutable and rejects unknown fields.

| Field | Default | Purpose |
|---|---|---|
| `allow_agent_skill_creation` | `True` | Accept agent-generated revisions |
| `require_human_approval` | `False` | Hold generated revisions for review |
| `max_document_bytes` | `1_000_000` | YAML input limit |
| `capability_candidate_limit` | `50` | MCP candidates per name |
| `capability_cache_size` | `1024` | Bounded cache; zero disables |
| `feedback_context_limit` | `20` | Rejections supplied when regenerating |
| `error_history_size` | `100` | Bounded observability failure history |

```python
from skill_manager import SkillManager, SkillManagerConfig

manager = SkillManager(
    config=SkillManagerConfig(
        require_human_approval=True,
        max_document_bytes=250_000,
        capability_cache_size=256,
    )
)
```

Call `await manager.aclose()` or use an async context manager. Injected sources,
registries, downstream runtimes and sinks remain caller-owned. The manager closes
only its default feedback manager and the scheduler started by `schedule_refresh`.

The package reads no environment variables. Examples use the variables listed in
[.env.example](https://github.com/smuniharish/skill-manager/blob/master/.env.example).
