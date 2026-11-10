"""Reproducible discovery measurements; no network or optional framework."""

from __future__ import annotations

import asyncio
import json
import time
import tracemalloc

from skill_manager import PipelineDiscoveryProvider, Skill, SkillMetadata


async def main() -> None:
    tracemalloc.start()
    start = time.perf_counter()
    skills = tuple(
        Skill(
            metadata=SkillMetadata(
                name=f"procedure-{index}",
                version="1.0.0",
                description=f"Catalog procedure {index} for support tasks.",
            ),
            instructions=("Apply the documented procedure.",),
        )
        for index in range(10_000)
    )
    construction = time.perf_counter() - start
    discovery = PipelineDiscoveryProvider()
    start = time.perf_counter()
    await discovery.index(skills)
    index = time.perf_counter() - start
    start = time.perf_counter()
    matches = await discovery.discover("support tasks", top_k=10)
    query = time.perf_counter() - start
    start = time.perf_counter()
    await asyncio.gather(*(discovery.discover("support tasks") for _ in range(100)))
    concurrent = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        json.dumps(
            {
                "catalog_size": len(skills),
                "model_construction_seconds": construction,
                "index_seconds": index,
                "top10_seconds": query,
                "100_queries_seconds": concurrent,
                "result_count": len(matches),
                "current_traced_bytes": current,
                "peak_traced_bytes": peak,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
