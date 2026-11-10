"""PostgreSQL Skill source and registry.

Install with ``pip install 'agskillmanager[postgres]'``. Both classes take a
psycopg ``AsyncConnectionPool``; the caller opens it, and the class closes it in
``aclose`` only when constructed with ``owns_pool=True``. Call `ensure_schema`
once to create the table and indexes. On Windows, run psycopg's async API on a
selector event loop: ``asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)``.
"""

from __future__ import annotations

import re
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from skill_manager._optional import optional_import
from skill_manager.errors import SkillConflictError, SkillNotFoundError, SkillSourceError
from skill_manager.models import Skill, SkillLifecycleState
from skill_manager.registry import SkillRegistry, check_write, latest
from skill_manager.sources import SkillSource, validate_source_id
from skill_manager.validation import dump_skill_yaml

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable, Mapping

    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

_psycopg = optional_import("psycopg", "postgres")
_sql = optional_import("psycopg.sql", "postgres")
_Jsonb = optional_import("psycopg.types.json", "postgres").Jsonb
_TABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
_ACTIVE = SkillLifecycleState.ACTIVE.value


def _table(name: str) -> Any:
    if not _TABLE.fullmatch(name):
        raise ValueError("table must be a plain SQL identifier of at most 63 characters")
    return _sql.Identifier(name)


@asynccontextmanager
async def _borrow(
    pool: AsyncConnectionPool[Any], message: str
) -> AsyncGenerator[AsyncConnection[Any]]:
    """Borrow a pooled connection, translating database errors into Skill errors."""
    try:
        async with pool.connection() as connection:
            yield connection
    except _psycopg.errors.UniqueViolation as error:
        raise SkillConflictError("a concurrent write created a second active revision") from error
    except _psycopg.Error as error:
        raise SkillSourceError(message) from error


class _PoolOwner:
    def __init__(self, pool: AsyncConnectionPool[Any], *, owns_pool: bool) -> None:
        self._pool = pool
        self._owns_pool = owns_pool

    async def aclose(self) -> None:
        """Close the pool when this object owns it."""
        if self._owns_pool:
            await self._pool.close()


class PostgresSkillSource(_PoolOwner, SkillSource):
    """Store Skill YAML documents in one PostgreSQL table, keyed by source and Skill ID.

    Several sources can share a table under different ``source_id`` values.

    Args:
        pool: Open psycopg async connection pool.
        source_id: Stable identifier for this source.
        table: Table name; created by `ensure_schema`.
        owns_pool: Close ``pool`` in `aclose`.
    """

    def __init__(
        self,
        pool: AsyncConnectionPool[Any],
        *,
        source_id: str = "postgres",
        table: str = "skill_manager_documents",
        owns_pool: bool = False,
    ) -> None:
        super().__init__(pool, owns_pool=owns_pool)
        self._source_id = validate_source_id(source_id)
        self._table = _table(table)

    @property
    def source_id(self) -> str:
        """Return the configured source identifier."""
        return self._source_id

    async def ensure_schema(self) -> None:
        """Create the document table if it does not exist."""
        await self._execute(
            "CREATE TABLE IF NOT EXISTS {table} ("
            " source_id text NOT NULL,"
            " skill_id text NOT NULL,"
            " document text NOT NULL,"
            " updated_at timestamptz NOT NULL DEFAULT now(),"
            " PRIMARY KEY (source_id, skill_id))",
            (),
            "cannot create the Skill document table",
        )

    async def load(self) -> Mapping[str, str]:
        """Return every document of this source, keyed by Skill ID."""
        rows = await self._execute(
            "SELECT skill_id, document FROM {table} WHERE source_id = %s ORDER BY skill_id",
            (self._source_id,),
            f"cannot load PostgreSQL Skill source {self._source_id!r}",
            fetch=True,
        )
        return dict(rows)

    async def save(self, skill: Skill) -> None:
        """Insert or replace the document of ``skill``."""
        await self._execute(
            "INSERT INTO {table} (source_id, skill_id, document) VALUES (%s, %s, %s)"
            " ON CONFLICT (source_id, skill_id)"
            " DO UPDATE SET document = EXCLUDED.document, updated_at = now()",
            (self._source_id, skill.skill_id, dump_skill_yaml(skill)),
            f"cannot persist Skill {skill.skill_id!r}",
        )

    async def delete(self, skill_id: str) -> None:
        """Delete the document of ``skill_id``, if present."""
        await self._execute(
            "DELETE FROM {table} WHERE source_id = %s AND skill_id = %s",
            (self._source_id, skill_id),
            f"cannot delete Skill {skill_id!r}",
        )

    async def _execute(
        self, query: str, params: tuple[Any, ...], message: str, *, fetch: bool = False
    ) -> list[Any]:
        async with _borrow(self._pool, message) as connection:
            cursor = await connection.execute(_sql.SQL(query).format(table=self._table), params)
            return await cursor.fetchall() if fetch else []


class PostgresSkillRegistry(_PoolOwner, SkillRegistry):
    """Shared Skill catalog in PostgreSQL, safe across processes.

    A partial unique index guarantees one ``ACTIVE`` revision per name and
    version, even under concurrent writers; a lost race raises
    `SkillConflictError`.

    Args:
        pool: Open psycopg async connection pool.
        table: Table name; created by `ensure_schema`.
        owns_pool: Close ``pool`` in `aclose`.
    """

    def __init__(
        self,
        pool: AsyncConnectionPool[Any],
        *,
        table: str = "skill_manager_skills",
        owns_pool: bool = False,
    ) -> None:
        super().__init__(pool, owns_pool=owns_pool)
        self._table = _table(table)
        self._active_index = _sql.Identifier(
            f"sm_active_{sha256(table.encode('ascii')).hexdigest()[:32]}"
        )

    async def ensure_schema(self) -> None:
        """Create the catalog table and its indexes if they do not exist."""
        statements = (
            "CREATE TABLE IF NOT EXISTS {table} ("
            " skill_id text PRIMARY KEY,"
            " name text NOT NULL,"
            " version text NOT NULL,"
            " revision integer NOT NULL,"
            " state text NOT NULL,"
            " document jsonb NOT NULL)",
            "CREATE UNIQUE INDEX IF NOT EXISTS {active} ON {table} (name, version)"
            " WHERE state = 'ACTIVE'",
        )
        async with self._connection() as connection:
            for statement in statements:
                await connection.execute(self._sql(statement))

    async def put(self, skill: Skill) -> None:
        """Insert or idempotently rewrite one revision."""
        async with self._connection() as connection, connection.transaction():
            await self._check(connection, skill, lock=True)
            await connection.execute(
                self._sql(
                    "INSERT INTO {table} (skill_id, name, version, revision, state, document)"
                    " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (skill_id) DO UPDATE SET"
                    " revision = EXCLUDED.revision, state = EXCLUDED.state,"
                    " document = EXCLUDED.document"
                ),
                (
                    skill.skill_id,
                    skill.metadata.name,
                    skill.metadata.version,
                    skill.revision,
                    skill.lifecycle.state.value,
                    _Jsonb(skill.model_dump(mode="json")),
                ),
            )

    async def check_put(self, skill: Skill) -> None:
        """Validate a write without applying it."""
        async with self._connection() as connection:
            await self._check(connection, skill, lock=False)

    async def get(self, skill_id: str) -> Skill:
        """Return a Skill by ID."""
        rows = await self._fetch("SELECT document FROM {table} WHERE skill_id = %s", (skill_id,))
        if not rows:
            raise SkillNotFoundError(f"Skill {skill_id!r} was not found")
        return Skill.model_validate(rows[0][0])

    async def by_name(self, name: str, version: str | None = None) -> Skill:
        """Return the active Skill with ``name`` and optional exact ``version``."""
        rows = await self._fetch(
            "SELECT document FROM {table} WHERE name = %s AND state = %s"
            " AND (%s::text IS NULL OR version = %s)",
            (name, _ACTIVE, version, version),
        )
        if not rows:
            raise SkillNotFoundError(f"Skill {name!r} version {version!r} was not found")
        return latest(Skill.model_validate(row[0]) for row in rows)

    async def all(
        self, *, states: Iterable[SkillLifecycleState] | None = None
    ) -> tuple[Skill, ...]:
        """Return every Skill, optionally filtered by lifecycle state."""
        if states is None:
            rows = await self._fetch("SELECT document FROM {table} ORDER BY skill_id", ())
        else:
            rows = await self._fetch(
                "SELECT document FROM {table} WHERE state = ANY(%s) ORDER BY skill_id",
                ([state.value for state in states],),
            )
        return tuple(Skill.model_validate(row[0]) for row in rows)

    async def remove(self, skill_id: str) -> Skill:
        """Remove and return one revision."""
        rows = await self._fetch(
            "DELETE FROM {table} WHERE skill_id = %s RETURNING document", (skill_id,)
        )
        if not rows:
            raise SkillNotFoundError(f"Skill {skill_id!r} was not found")
        return Skill.model_validate(rows[0][0])

    async def replace_lifecycle(self, skill: Skill) -> None:
        """Overwrite an existing revision after a lifecycle transition."""
        async with self._connection() as connection, connection.transaction():
            cursor = await connection.execute(
                self._sql("SELECT 1 FROM {table} WHERE skill_id = %s FOR UPDATE"),
                (skill.skill_id,),
            )
            if await cursor.fetchone() is None:
                raise SkillNotFoundError(f"Skill {skill.skill_id!r} was not found")
            if skill.lifecycle.state is SkillLifecycleState.ACTIVE and await self._peers(
                connection, skill
            ):
                raise SkillConflictError(
                    f"another active revision already exists for {skill.metadata.name!r}"
                )
            await connection.execute(
                self._sql(
                    "UPDATE {table} SET revision = %s, state = %s, document = %s"
                    " WHERE skill_id = %s"
                ),
                (
                    skill.revision,
                    skill.lifecycle.state.value,
                    _Jsonb(skill.model_dump(mode="json")),
                    skill.skill_id,
                ),
            )

    async def _check(self, connection: AsyncConnection[Any], skill: Skill, *, lock: bool) -> None:
        cursor = await connection.execute(
            self._sql(
                "SELECT document FROM {table} WHERE skill_id = %s FOR UPDATE"
                if lock
                else "SELECT document FROM {table} WHERE skill_id = %s"
            ),
            (skill.skill_id,),
        )
        row = await cursor.fetchone()
        existing = Skill.model_validate(row[0]) if row is not None else None
        check_write(existing, skill, await self._peers(connection, skill))

    async def _peers(self, connection: AsyncConnection[Any], skill: Skill) -> list[str]:
        cursor = await connection.execute(
            self._sql(
                "SELECT skill_id FROM {table} WHERE name = %s AND version = %s"
                " AND state = %s AND skill_id <> %s"
            ),
            (skill.metadata.name, skill.metadata.version, _ACTIVE, skill.skill_id),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def _fetch(self, query: str, params: tuple[Any, ...]) -> list[Any]:
        async with self._connection() as connection:
            cursor = await connection.execute(self._sql(query), params)
            return await cursor.fetchall()

    def _sql(self, query: str) -> Any:
        return _sql.SQL(query).format(table=self._table, active=self._active_index)

    def _connection(self) -> AbstractAsyncContextManager[AsyncConnection[Any]]:
        return _borrow(self._pool, "PostgreSQL Skill registry operation failed")


__all__ = ["PostgresSkillRegistry", "PostgresSkillSource"]
