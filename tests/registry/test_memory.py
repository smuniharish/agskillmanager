from __future__ import annotations

import pytest

from skill_manager import InMemorySkillRegistry, SkillConflictError, SkillLifecycleState
from skill_manager.registry import SkillRegistry, check_write, latest
from skill_manager.testing import SkillRegistryContract
from tests.helpers import make_skill


class TestInMemorySkillRegistry(SkillRegistryContract):
    async def make_registry(self) -> SkillRegistry:
        return InMemorySkillRegistry()


def test_check_write_rules() -> None:
    skill = make_skill()
    check_write(None, skill, [skill.skill_id])
    check_write(skill, skill, [])
    pending = make_skill(state=SkillLifecycleState.PENDING_APPROVAL)
    check_write(None, pending, ["other"])
    with pytest.raises(SkillConflictError, match="multiple active"):
        check_write(None, skill, ["other"])
    with pytest.raises(SkillConflictError, match="stale"):
        check_write(skill.model_copy(update={"revision": 2}), skill, [])
    with pytest.raises(SkillConflictError, match="immutable"):
        check_write(skill, skill.model_copy(update={"instructions": ("Other.",)}), [])


def test_latest_breaks_ties_by_id() -> None:
    first, second = make_skill(), make_skill()
    assert latest([first, second]) == max(first, second, key=lambda item: item.skill_id)


async def test_removing_one_of_two_revisions_keeps_the_other() -> None:
    registry = InMemorySkillRegistry()
    active = make_skill()
    pending = make_skill(state=SkillLifecycleState.PENDING_APPROVAL)
    await registry.put(active)
    await registry.put(pending)
    await registry.remove(pending.skill_id)
    assert await registry.by_name(active.metadata.name) == active
    await registry.aclose()
