"""Conformance tests for `SkillSource` and `SkillRegistry` implementations.

Subclass a contract in a test module and implement its factory; your test
runner collects one test per promise of the contract:

```python
from skill_manager.testing import SkillRegistryContract


class TestMyRegistry(SkillRegistryContract):
    async def make_registry(self):
        registry = MyRegistry(dsn)
        await registry.truncate()  # every test starts from an empty catalog
        return registry
```

Each test calls ``aclose`` on the object it made. The tests are plain
synchronous methods that raise `AssertionError` with a descriptive message, so
they run under pytest, or under unittest when the subclass also inherits
``unittest.TestCase``. Neither pytest nor an async plugin is required. Set
``loop_factory`` to choose the event loop, for example
``asyncio.SelectorEventLoop`` for psycopg on Windows.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from skill_manager.errors import SkillConflictError, SkillNotFoundError
from skill_manager.models import (
    Skill,
    SkillLifecycle,
    SkillLifecycleState,
    SkillMetadata,
)
from skill_manager.validation import parse_skill_yaml

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from skill_manager.registry import SkillRegistry
    from skill_manager.sources import SkillSource

__all__ = ["SkillRegistryContract", "SkillSourceContract"]


def _skill(
    name: str = "contract-skill",
    version: str = "1.0.0",
    *,
    state: SkillLifecycleState = SkillLifecycleState.ACTIVE,
) -> Skill:
    return Skill(
        metadata=SkillMetadata(name=name, version=version, description="Contract Skill."),
        instructions=("Follow the contract.",),
        lifecycle=SkillLifecycle(state=state),
    )


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _raises(error: type[Exception], operation: Awaitable[Any], message: str) -> None:
    try:
        await operation
    except error:
        return
    raise AssertionError(message)


class _Contract:
    loop_factory: ClassVar[Callable[[], asyncio.AbstractEventLoop] | None] = None

    def _run(self, coroutine: Coroutine[Any, Any, None]) -> None:
        asyncio.run(coroutine, loop_factory=self.loop_factory)


class SkillSourceContract(_Contract, ABC):
    """Promises every `SkillSource` keeps."""

    @abstractmethod
    async def make_source(self) -> SkillSource:
        """Return a new, empty source."""

    def _with_source(self, test: Callable[[SkillSource], Awaitable[None]]) -> None:
        async def run() -> None:
            source = await self.make_source()
            try:
                await test(source)
            finally:
                await source.aclose()

        self._run(run())

    def test_source_id_is_non_empty(self) -> None:
        """The source has a non-blank identifier."""

        async def test(source: SkillSource) -> None:
            _check(bool(source.source_id.strip()), "source_id must not be empty")

        self._with_source(test)

    def test_empty_source_loads_nothing(self) -> None:
        """A new source loads no documents."""

        async def test(source: SkillSource) -> None:
            _check(not await source.load(), "a new source must load no documents")

        self._with_source(test)

    def test_saved_skill_round_trips(self) -> None:
        """A saved Skill loads back as an equal Skill."""

        async def test(source: SkillSource) -> None:
            skill = _skill()
            await source.save(skill)
            documents = list((await source.load()).values())
            _check(len(documents) == 1, "load must return exactly the saved document")
            _check(
                await parse_skill_yaml(documents[0]) == skill,
                "the loaded document must parse back to the saved Skill",
            )

        self._with_source(test)

    def test_save_replaces_the_previous_document(self) -> None:
        """Saving a Skill again replaces its document."""

        async def test(source: SkillSource) -> None:
            pending = _skill(state=SkillLifecycleState.PENDING_APPROVAL)
            active = pending.model_copy(update={"lifecycle": SkillLifecycle()})
            await source.save(pending)
            await source.save(active)
            documents = list((await source.load()).values())
            _check(len(documents) == 1, "saving the same Skill twice must keep one document")
            _check(
                await parse_skill_yaml(documents[0]) == active,
                "the latest save must win",
            )

        self._with_source(test)

    def test_delete_removes_the_document(self) -> None:
        """Delete removes only the given Skill."""

        async def test(source: SkillSource) -> None:
            kept, deleted = _skill("kept-skill"), _skill("deleted-skill")
            await source.save(kept)
            await source.save(deleted)
            await source.delete(deleted.skill_id)
            documents = [await parse_skill_yaml(text) for text in (await source.load()).values()]
            _check(documents == [kept], "delete must remove only the given Skill")

        self._with_source(test)

    def test_delete_ignores_unknown_ids(self) -> None:
        """Deleting an unknown Skill is a no-op."""

        async def test(source: SkillSource) -> None:
            await source.delete(_skill().skill_id)

        self._with_source(test)


class SkillRegistryContract(_Contract, ABC):
    """Promises every `SkillRegistry` keeps."""

    @abstractmethod
    async def make_registry(self) -> SkillRegistry:
        """Return a new, empty registry."""

    def _with_registry(self, test: Callable[[SkillRegistry], Awaitable[None]]) -> None:
        async def run() -> None:
            registry = await self.make_registry()
            try:
                await test(registry)
            finally:
                await registry.aclose()

        self._run(run())

    def test_put_then_get(self) -> None:
        """A stored Skill is returned by ``get``."""

        async def test(registry: SkillRegistry) -> None:
            skill = _skill()
            await registry.put(skill)
            _check(await registry.get(skill.skill_id) == skill, "get must return the stored Skill")

        self._with_registry(test)

    def test_get_unknown_raises_not_found(self) -> None:
        """``get`` raises `SkillNotFoundError` for an unknown ID."""

        async def test(registry: SkillRegistry) -> None:
            await _raises(
                SkillNotFoundError,
                registry.get(_skill().skill_id),
                "get must raise SkillNotFoundError for an unknown ID",
            )

        self._with_registry(test)

    def test_identical_put_is_idempotent(self) -> None:
        """Storing the same Skill twice keeps one copy."""

        async def test(registry: SkillRegistry) -> None:
            skill = _skill()
            await registry.put(skill)
            await registry.put(skill)
            _check(len(await registry.all()) == 1, "an identical put must not duplicate")

        self._with_registry(test)

    def test_revision_is_immutable(self) -> None:
        """A stored revision cannot change content."""

        async def test(registry: SkillRegistry) -> None:
            skill = _skill()
            await registry.put(skill)
            changed = skill.model_copy(update={"instructions": ("Changed.",)})
            await _raises(
                SkillConflictError,
                registry.put(changed),
                "rewriting a revision with different content must conflict",
            )

        self._with_registry(test)

    def test_stale_revision_conflicts(self) -> None:
        """An older revision cannot replace a newer one."""

        async def test(registry: SkillRegistry) -> None:
            skill = _skill()
            await registry.put(skill.model_copy(update={"revision": 2}))
            await _raises(
                SkillConflictError, registry.put(skill), "an older revision must conflict"
            )

        self._with_registry(test)

    def test_one_active_revision_per_name_and_version(self) -> None:
        """Only one revision per name and version is ACTIVE."""

        async def test(registry: SkillRegistry) -> None:
            await registry.put(_skill())
            await _raises(
                SkillConflictError,
                registry.put(_skill()),
                "a second ACTIVE revision of the same name and version must conflict",
            )
            await _raises(
                SkillConflictError,
                registry.check_put(_skill()),
                "check_put must report the same conflict",
            )
            await registry.put(_skill(state=SkillLifecycleState.PENDING_APPROVAL))

        self._with_registry(test)

    def test_check_put_does_not_write(self) -> None:
        """``check_put`` validates without storing."""

        async def test(registry: SkillRegistry) -> None:
            await registry.check_put(_skill())
            _check(not await registry.all(), "check_put must not store the Skill")

        self._with_registry(test)

    def test_by_name_returns_highest_active_version(self) -> None:
        """``by_name`` resolves the highest ACTIVE version."""

        async def test(registry: SkillRegistry) -> None:
            old, new = _skill(version="1.2.0"), _skill(version="1.10.0")
            await registry.put(old)
            await registry.put(new)
            await registry.put(_skill(version="2.0.0", state=SkillLifecycleState.REJECTED))
            _check(await registry.by_name(old.metadata.name) == new, "by_name must pick 1.10.0")
            _check(
                await registry.by_name(old.metadata.name, "1.2.0") == old,
                "by_name with a version must return that version",
            )
            await _raises(
                SkillNotFoundError,
                registry.by_name(old.metadata.name, "2.0.0"),
                "by_name must ignore inactive revisions",
            )

        self._with_registry(test)

    def test_all_filters_by_state(self) -> None:
        """``all`` returns every Skill, optionally filtered by state."""

        async def test(registry: SkillRegistry) -> None:
            active = _skill("active-skill")
            pending = _skill("pending-skill", state=SkillLifecycleState.PENDING_APPROVAL)
            await registry.put(active)
            await registry.put(pending)
            everything = {skill.skill_id: skill for skill in await registry.all()}
            _check(
                everything == {active.skill_id: active, pending.skill_id: pending},
                "all must return everything",
            )
            _check(
                await registry.all(states={SkillLifecycleState.PENDING_APPROVAL}) == (pending,),
                "all must filter by state",
            )

        self._with_registry(test)

    def test_remove(self) -> None:
        """``remove`` deletes and returns the Skill."""

        async def test(registry: SkillRegistry) -> None:
            skill = _skill()
            await registry.put(skill)
            _check(await registry.remove(skill.skill_id) == skill, "remove must return the Skill")
            await _raises(
                SkillNotFoundError,
                registry.remove(skill.skill_id),
                "remove must raise SkillNotFoundError for an unknown ID",
            )

        self._with_registry(test)

    def test_replace_lifecycle(self) -> None:
        """``replace_lifecycle`` persists a lifecycle transition."""

        async def test(registry: SkillRegistry) -> None:
            pending = _skill(state=SkillLifecycleState.PENDING_APPROVAL)
            await registry.put(pending)
            active = pending.model_copy(update={"lifecycle": SkillLifecycle()})
            await registry.replace_lifecycle(active)
            _check(await registry.get(pending.skill_id) == active, "the transition must persist")
            await _raises(
                SkillNotFoundError,
                registry.replace_lifecycle(_skill("unknown-skill")),
                "replace_lifecycle must raise SkillNotFoundError for an unknown ID",
            )

        self._with_registry(test)

    def test_replace_lifecycle_keeps_one_active_revision(self) -> None:
        """Activation cannot create a second ACTIVE revision."""

        async def test(registry: SkillRegistry) -> None:
            await registry.put(_skill())
            pending = _skill(state=SkillLifecycleState.PENDING_APPROVAL)
            await registry.put(pending)
            await _raises(
                SkillConflictError,
                registry.replace_lifecycle(
                    pending.model_copy(update={"lifecycle": SkillLifecycle()})
                ),
                "activating a second revision must conflict",
            )

        self._with_registry(test)
