"""Persist a catalog using an injected psycopg async pool."""

import asyncio
import os
import sys
from uuid import uuid4

from _shared import sample_skill, show
from psycopg import sql
from psycopg_pool import AsyncConnectionPool

from skill_manager import SkillManager
from skill_manager.postgres import PostgresSkillRegistry, PostgresSkillSource


async def main() -> None:
    dsn = os.environ["SKILL_MANAGER_POSTGRES_DSN"]
    table = f"example_skills_{uuid4().hex}"
    documents = f"example_docs_{uuid4().hex}"
    async with AsyncConnectionPool(dsn, open=False) as pool:
        registry = PostgresSkillRegistry(pool, table=table)
        source = PostgresSkillSource(pool, table=documents)
        await registry.ensure_schema()
        await source.ensure_schema()
        try:
            async with SkillManager(registry=registry, sources=[source]) as manager:
                skill = await manager.register_skill(sample_skill())
                show("PostgreSQL catalog", (await manager.load(skill.skill_id)).metadata.name)
        finally:
            async with pool.connection() as connection:
                await connection.execute(
                    sql.SQL("DROP TABLE {}, {}").format(
                        sql.Identifier(table), sql.Identifier(documents)
                    )
                )


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
