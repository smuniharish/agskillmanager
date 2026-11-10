from __future__ import annotations

import time

import pytest

from skill_manager import PipelineDiscoveryProvider
from tests.helpers import make_skill


@pytest.mark.benchmark
async def test_lexical_discovery_over_two_thousand_skills() -> None:
    provider = PipelineDiscoveryProvider()
    skills = tuple(make_skill(f"procedure-{index}") for index in range(2000))
    await provider.index(skills)
    start = time.perf_counter()
    matches = await provider.discover("procedure-1999", top_k=1)
    assert matches == [skills[-1]]
    assert time.perf_counter() - start < 2.0
