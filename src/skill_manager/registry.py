"""Skill catalog contract and its in-memory implementation."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from packaging.version import Version

from skill_manager.errors import SkillConflictError, SkillNotFoundError
from skill_manager.models import Skill, SkillLifecycleState

if TYPE_CHECKING:
    from collections.abc import Iterable


class SkillRegistry(ABC):
    """Validated Skill catalog used by `SkillManager`.

    Implementations may keep the catalog in process (`InMemorySkillRegistry`) or
    in a shared database (`skill_manager.postgres.PostgresSkillRegistry`). Every
    implementation must keep these promises, which
    `skill_manager.testing.SkillRegistryContract` verifies:

    - A revision is immutable: writing a different Skill with the same ID and
      revision raises `SkillConflictError`, and writing an older revision is a
      stale update that raises `SkillConflictError`.
    - At most one ``ACTIVE`` revision exists per name and version.
    - `get` and `remove` raise `SkillNotFoundError` for unknown IDs.
    """

    @abstractmethod
    async def put(self, skill: Skill) -> None:
        """Insert a Skill revision, or idempotently rewrite an identical one."""

    @abstractmethod
    async def check_put(self, skill: Skill) -> None:
        """Raise the error `put` would raise, without writing anything."""

    @abstractmethod
    async def get(self, skill_id: str) -> Skill:
        """Return a Skill by immutable ID."""

    @abstractmethod
    async def by_name(self, name: str, version: str | None = None) -> Skill:
        """Return the active Skill with ``name``.

        Without ``version``, return the highest PEP 440 version.
        """

    @abstractmethod
    async def all(
        self, *, states: Iterable[SkillLifecycleState] | None = None
    ) -> tuple[Skill, ...]:
        """Return every Skill, optionally only those in ``states``."""

    @abstractmethod
    async def remove(self, skill_id: str) -> Skill:
        """Remove and return one Skill revision."""

    @abstractmethod
    async def replace_lifecycle(self, skill: Skill) -> None:
        """Overwrite an existing Skill after a lifecycle transition."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook with a no-op default
        """Release resources; the default does nothing."""


def check_write(existing: Skill | None, skill: Skill, active_peers: Iterable[str]) -> None:
    """Apply the registry write rules shared by every implementation.

    Args:
        existing: The stored revision with the same ID, if any.
        skill: The revision being written.
        active_peers: IDs of other ``ACTIVE`` revisions with the same name and version.

    Raises:
        SkillConflictError: If the write is stale, overwrites an immutable
            revision, or creates a second active revision.
    """
    if skill.lifecycle.state is SkillLifecycleState.ACTIVE and any(
        peer != skill.skill_id for peer in active_peers
    ):
        raise SkillConflictError(
            f"multiple active revisions for Skill {skill.metadata.name!r} "
            f"version {skill.metadata.version!r}"
        )
    if existing is None:
        return
    if existing.revision > skill.revision:
        raise SkillConflictError(f"stale update for Skill {skill.skill_id!r}")
    if existing.revision == skill.revision and existing != skill:
        raise SkillConflictError(
            f"immutable Skill revision {skill.skill_id!r} cannot be overwritten"
        )


def latest(skills: Iterable[Skill]) -> Skill:
    """Return the Skill with the highest PEP 440 version, breaking ties by ID."""
    return max(skills, key=lambda item: (Version(item.metadata.version), item.skill_id))


class InMemorySkillRegistry(SkillRegistry):
    """Concurrency-safe, process-local Skill registry."""

    def __init__(self) -> None:
        self._by_id: dict[str, Skill] = {}
        self._by_key: dict[tuple[str, str], set[str]] = {}
        self._lock = asyncio.Lock()

    def _active_peers(self, skill: Skill) -> set[str]:
        key = (skill.metadata.name, skill.metadata.version)
        return {
            skill_id
            for skill_id in self._by_key.get(key, ())
            if self._by_id[skill_id].lifecycle.state is SkillLifecycleState.ACTIVE
        }

    async def put(self, skill: Skill) -> None:
        """Insert or idempotently rewrite one revision."""
        async with self._lock:
            check_write(self._by_id.get(skill.skill_id), skill, self._active_peers(skill))
            self._by_id[skill.skill_id] = skill
            self._by_key.setdefault((skill.metadata.name, skill.metadata.version), set()).add(
                skill.skill_id
            )

    async def check_put(self, skill: Skill) -> None:
        """Validate a write without applying it."""
        async with self._lock:
            check_write(self._by_id.get(skill.skill_id), skill, self._active_peers(skill))

    async def get(self, skill_id: str) -> Skill:
        """Return a Skill by ID."""
        async with self._lock:
            try:
                return self._by_id[skill_id]
            except KeyError:
                raise SkillNotFoundError(f"Skill {skill_id!r} was not found") from None

    async def by_name(self, name: str, version: str | None = None) -> Skill:
        """Return the active Skill with ``name`` and optional exact ``version``."""
        async with self._lock:
            matches = [
                skill
                for (skill_name, skill_version), ids in self._by_key.items()
                if skill_name == name and version in {None, skill_version}
                for skill_id in ids
                if (skill := self._by_id[skill_id]).lifecycle.state is SkillLifecycleState.ACTIVE
            ]
        if not matches:
            raise SkillNotFoundError(f"Skill {name!r} version {version!r} was not found")
        return latest(matches)

    async def all(
        self, *, states: Iterable[SkillLifecycleState] | None = None
    ) -> tuple[Skill, ...]:
        """Return every Skill, optionally filtered by lifecycle state."""
        async with self._lock:
            values = tuple(self._by_id.values())
        if states is None:
            return values
        wanted = frozenset(states)
        return tuple(skill for skill in values if skill.lifecycle.state in wanted)

    async def remove(self, skill_id: str) -> Skill:
        """Remove and return one revision."""
        async with self._lock:
            try:
                skill = self._by_id.pop(skill_id)
            except KeyError:
                raise SkillNotFoundError(f"Skill {skill_id!r} was not found") from None
            key = (skill.metadata.name, skill.metadata.version)
            ids = self._by_key[key]
            ids.discard(skill_id)
            if not ids:
                del self._by_key[key]
            return skill

    async def replace_lifecycle(self, skill: Skill) -> None:
        """Overwrite an existing revision after a lifecycle transition."""
        async with self._lock:
            if skill.skill_id not in self._by_id:
                raise SkillNotFoundError(f"Skill {skill.skill_id!r} was not found")
            if skill.lifecycle.state is SkillLifecycleState.ACTIVE and (
                self._active_peers(skill) - {skill.skill_id}
            ):
                raise SkillConflictError(
                    f"another active revision already exists for {skill.metadata.name!r}"
                )
            self._by_id[skill.skill_id] = skill


__all__ = ["InMemorySkillRegistry", "SkillRegistry", "check_write", "latest"]
