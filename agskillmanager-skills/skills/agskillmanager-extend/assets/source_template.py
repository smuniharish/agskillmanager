"""A complete, copyable source; replace dictionary operations for your backend."""

from __future__ import annotations

from skill_manager import Skill, SkillSource, dump_skill_yaml
from skill_manager.sources import validate_source_id


class MemorySkillSource(SkillSource):
    def __init__(self, source_id: str = "custom") -> None:
        self._id = validate_source_id(source_id)
        self._documents: dict[str, str] = {}

    @property
    def source_id(self) -> str:
        return self._id

    async def load(self) -> dict[str, str]:
        return dict(self._documents)

    async def save(self, skill: Skill) -> None:
        self._documents[skill.skill_id] = dump_skill_yaml(skill)

    async def delete(self, skill_id: str) -> None:
        self._documents.pop(skill_id, None)
