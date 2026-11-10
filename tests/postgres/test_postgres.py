from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from psycopg import OperationalError, errors, sql
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from skill_manager import SkillConflictError, SkillSourceError
from skill_manager.postgres import PostgresSkillRegistry, PostgresSkillSource, _borrow
from skill_manager.testing import SkillRegistryContract, SkillSourceContract
from tests.helpers import make_skill

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

DSN = os.getenv("SKILL_MANAGER_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.postgres


class OwnedRegistry(PostgresSkillRegistry):
    async def aclose(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(sql.SQL("DROP TABLE {}").format(self._table))
        await super().aclose()


class OwnedSource(PostgresSkillSource):
    async def aclose(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(sql.SQL("DROP TABLE {}").format(self._table))
        await super().aclose()


@pytest.mark.skipif(not DSN, reason="set SKILL_MANAGER_TEST_POSTGRES_DSN")
class TestPostgresRegistry(SkillRegistryContract):
    loop_factory = asyncio.SelectorEventLoop

    async def make_registry(self) -> PostgresSkillRegistry:
        assert DSN
        pool = AsyncConnectionPool(DSN, open=False)
        await pool.open(wait=True)
        registry = OwnedRegistry(pool, table=f"test_registry_{uuid4().hex}", owns_pool=True)
        await registry.ensure_schema()
        return registry


@pytest.mark.skipif(not DSN, reason="set SKILL_MANAGER_TEST_POSTGRES_DSN")
class TestPostgresSource(SkillSourceContract):
    loop_factory = asyncio.SelectorEventLoop

    async def make_source(self) -> PostgresSkillSource:
        assert DSN
        pool = AsyncConnectionPool(DSN, open=False)
        await pool.open(wait=True)
        source = OwnedSource(pool, table=f"test_source_{uuid4().hex}", owns_pool=True)
        await source.ensure_schema()
        return source


def test_table_identifiers() -> None:
    pool = AsyncConnectionPool(open=False)
    for bad in ("", "a; DROP TABLE users", "x" * 64, "public.skills"):
        with pytest.raises(ValueError, match="identifier"):
            PostgresSkillSource(pool, table=bad)
        with pytest.raises(ValueError, match="identifier"):
            PostgresSkillRegistry(pool, table=bad)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (errors.UniqueViolation("duplicate"), SkillConflictError),
        (OperationalError("offline"), SkillSourceError),
    ],
)
async def test_database_errors_are_translated(
    error: Exception, expected: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = AsyncConnectionPool(open=False)

    @asynccontextmanager
    async def fail() -> AsyncGenerator[None, None]:
        raise error
        yield

    monkeypatch.setattr(pool, "connection", fail)
    with pytest.raises(expected):
        async with _borrow(pool, "database unavailable"):
            pytest.fail("connection should not open")
    await pool.close()


async def test_borrowed_pool_is_not_closed() -> None:
    pool = AsyncConnectionPool(open=False)
    await PostgresSkillSource(pool).aclose()
    await PostgresSkillRegistry(pool).aclose()
    await pool.close()


@pytest.mark.skipif(not DSN, reason="set SKILL_MANAGER_TEST_POSTGRES_DSN")
def test_long_table_names_keep_the_active_revision_index() -> None:
    async def verify() -> None:
        assert DSN
        async with AsyncConnectionPool(DSN, open=False) as pool:
            table = f"test_{uuid4().hex}_{'x' * 25}"
            registry = OwnedRegistry(pool, table=table)
            await registry.ensure_schema()
            try:
                await registry.ensure_schema()
                async with pool.connection() as connection:
                    cursor = await connection.execute(
                        "SELECT indexname FROM pg_indexes"
                        " WHERE schemaname = current_schema() AND tablename = %s"
                        " AND indexdef LIKE %s",
                        (table, "% WHERE %"),
                    )
                    indexes = await cursor.fetchall()
                assert len(indexes) == 1
                assert indexes[0][0] != table
                assert len(indexes[0][0]) <= 63
                first, second = make_skill(), make_skill()
                await registry.put(first)
                with pytest.raises(errors.UniqueViolation):
                    async with pool.connection() as connection:
                        await connection.execute(
                            sql.SQL(
                                "INSERT INTO {}"
                                " (skill_id, name, version, revision, state, document)"
                                " VALUES (%s, %s, %s, %s, %s, %s)"
                            ).format(sql.Identifier(table)),
                            (
                                second.skill_id,
                                second.metadata.name,
                                second.metadata.version,
                                second.revision,
                                second.lifecycle.state.value,
                                Jsonb(second.model_dump(mode="json")),
                            ),
                        )
            finally:
                await registry.aclose()

    asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)
