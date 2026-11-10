# Sources and storage

Sources store YAML; registries index validated revisions. They are separate ABCs.

```python
from skill_manager import FilesystemSkillSource, SkillManager


async def open_catalog():
    source = FilesystemSkillSource("skills", source_id="team")
    async with SkillManager(sources=[source]) as manager:
        return await manager.list_skills()
```

The first source is the default write target. Pass `source_id=` to register or
generate into a specific source. IDs must be unique; keep ownership of individual
Skill IDs unambiguous across sources.

Filesystem sources read `.yaml` and `.yml`, refuse symlinks and path escapes,
and atomically replace files. Loaded filenames are preserved. Malformed documents
appear in `source_errors`; healthy entries remain available. During refresh,
malformed replacements retain the last valid revision.

## PostgreSQL

Install `skill-manager[postgres]`. Pass an open psycopg `AsyncConnectionPool` to
`PostgresSkillRegistry` and/or `PostgresSkillSource`; call `ensure_schema()` once.
Tables use validated identifiers and bound parameters. Transactions and a partial
unique index enforce one active revision per name/version across processes.
Index names are deterministic and bounded independently of the table name,
including PostgreSQL's full 63-character table-name limit.

Pools stay caller-owned unless `owns_pool=True`. On Windows use
`asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)` for psycopg.
See the [PostgreSQL example](../examples/index.md#service-backed-examples).

## Custom backends

Subclass `SkillSource` or `SkillRegistry`, implement every abstract async method,
then run the shipped `SkillSourceContract` or `SkillRegistryContract`.
See [extension APIs](../api/extensions.md) and [Agent Skills](../agent-skills/index.md).
