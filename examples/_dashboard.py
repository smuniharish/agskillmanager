"""A serialized synchronous boundary for Streamlit's rerun-based UI."""

from __future__ import annotations

import asyncio
import atexit
from threading import Lock
from typing import TYPE_CHECKING

from _shared import SampleGenerator, chat_model

from skill_manager import FilesystemSkillSource, Skill, SkillManager, SkillManagerConfig

if TYPE_CHECKING:
    from collections.abc import Coroutine


class Dashboard:
    def __init__(self, root: str) -> None:
        self._runner = asyncio.Runner()
        self._lock = Lock()
        self._closed = False
        self.manager = SkillManager(
            sources=[FilesystemSkillSource(root)],
            config=SkillManagerConfig(require_human_approval=True),
        )
        atexit.register(self.close)

    def _call[T](self, operation: Coroutine[object, object, T]) -> T:
        with self._lock:
            if self._closed:
                operation.close()
                raise RuntimeError("dashboard is closed")
            return self._runner.run(operation)

    def skills(self) -> tuple[Skill, ...]:
        return self._call(self.manager.list_skills())

    def register(self, skill: Skill) -> Skill:
        return self._call(self.manager.register_skill(skill))

    def generate(self, prompt: str, *, model: bool = False, parent: str | None = None) -> Skill:
        async def generate() -> Skill:
            if model:
                from skill_manager.integrations.langchain import XStructuredSkillGenerator

                async with chat_model() as runnable:
                    return await self.manager.generate_skill(
                        XStructuredSkillGenerator(runnable), prompt, parent_skill_id=parent
                    )
            return await self.manager.generate_skill(
                SampleGenerator(), prompt, parent_skill_id=parent
            )

        return self._call(generate())

    def approve(self, skill_id: str, reviewer: str) -> Skill:
        return self._call(self.manager.approve_skill(skill_id, reviewer=reviewer))

    def reject(self, skill_id: str, reviewer: str, feedback: str) -> Skill:
        return self._call(self.manager.reject_skill(skill_id, reviewer=reviewer, feedback=feedback))

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._runner.run(self.manager.aclose())
                self._runner.close()
                self._closed = True
