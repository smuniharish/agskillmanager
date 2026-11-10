"""Skill source contract and a safe filesystem implementation."""

from __future__ import annotations

import asyncio
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

from skill_manager.errors import SkillSourceError
from skill_manager.models import Skill, is_skill_id
from skill_manager.validation import dump_skill_yaml

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKILL_ID_LINE = re.compile(r"""^skill_id:\s*["']?(sk_[0-9A-HJKMNP-TV-Z]{26})["']?\s*$""", re.M)


def validate_source_id(source_id: str) -> str:
    """Return ``source_id`` when it is a non-empty, single-line identifier of at most 128 chars."""
    if (
        not source_id.strip()
        or len(source_id) > 128
        or any(character in source_id for character in "\r\n\x00")
    ):
        raise ValueError("source_id must be a non-empty safe identifier")
    return source_id


class SkillSource(ABC):
    """Where Skills originate; each source owns its own persistence.

    A source stores Skill YAML documents. `SkillManager` parses and validates
    them, so a source never interprets YAML itself. Every implementation must
    keep these promises, which `skill_manager.testing.SkillSourceContract`
    verifies:

    - `load` returns every stored document keyed by a stable locator.
    - `save` creates or overwrites the document of ``skill.skill_id``, and the
      next `load` returns it exactly once.
    - `delete` removes the document and ignores unknown IDs.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Return a stable, non-secret source identifier."""

    @abstractmethod
    async def load(self) -> Mapping[str, str]:
        """Return locator to YAML text, without parsing or executing it."""

    @abstractmethod
    async def save(self, skill: Skill) -> None:
        """Persist one validated Skill revision, replacing its previous document."""

    @abstractmethod
    async def delete(self, skill_id: str) -> None:
        """Remove the document of a Skill; unknown IDs are ignored."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook with a no-op default
        """Release resources; the default does nothing."""


class FilesystemSkillSource(SkillSource):
    """Read and atomically write ``*.yaml`` and ``*.yml`` files in one directory.

    Symbolic links and paths escaping the root are refused. New Skills are
    written to ``<skill_id>.yaml``; a Skill loaded from another file name is
    rewritten in place.

    Args:
        root: Directory holding the Skill documents; created on first save.
        source_id: Stable identifier for this source.
    """

    def __init__(self, root: str | Path, *, source_id: str = "filesystem") -> None:
        self._root = Path(root).expanduser().resolve()
        self._source_id = validate_source_id(source_id)
        self._paths: dict[str, Path] = {}

    @property
    def source_id(self) -> str:
        """Return the configured source identifier."""
        return self._source_id

    @property
    def root(self) -> Path:
        """Return the resolved source directory."""
        return self._root

    async def load(self) -> Mapping[str, str]:
        """Read every Skill document in the root directory."""
        try:
            documents, paths = await asyncio.to_thread(self._load_sync)
        except OSError as error:
            raise SkillSourceError(
                f"cannot load filesystem Skill source {self.source_id!r}"
            ) from error
        self._paths = paths
        return documents

    def _safe(self, path: Path) -> Path:
        if path.is_symlink():
            raise SkillSourceError(f"symbolic links are not allowed in Skill sources: {path.name}")
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise SkillSourceError(f"Skill path escapes configured root: {path.name}")
        return resolved

    def _load_sync(self) -> tuple[dict[str, str], dict[str, Path]]:
        if not self._root.exists():
            return {}, {}
        if not self._root.is_dir():
            raise SkillSourceError(f"Skill source root is not a directory: {self._root}")
        documents: dict[str, str] = {}
        paths: dict[str, Path] = {}
        for path in sorted((*self._root.glob("*.yaml"), *self._root.glob("*.yml"))):
            text = self._safe(path).read_text(encoding="utf-8")
            documents[path.name] = text
            if match := _SKILL_ID_LINE.search(text):
                paths.setdefault(match.group(1), path)
        return documents, paths

    async def save(self, skill: Skill) -> None:
        """Atomically write the Skill document."""
        destination = self._paths.get(skill.skill_id, self._root / f"{skill.skill_id}.yaml")
        try:
            await asyncio.to_thread(self._save_sync, destination, dump_skill_yaml(skill))
        except OSError as error:
            raise SkillSourceError(f"cannot persist Skill {skill.skill_id!r}") from error
        self._paths[skill.skill_id] = destination

    def _save_sync(self, destination: Path, serialized: str) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self._safe(destination)
        temporary = NamedTemporaryFile(  # noqa: SIM115 - cleanup must also cover __enter__ failures
            mode="w",
            encoding="utf-8",
            dir=self._root,
            prefix=".skill-",
            suffix=".tmp",
            delete=False,
        )
        temporary_path = Path(temporary.name)
        try:
            with temporary:
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(destination)
        finally:
            temporary_path.unlink(missing_ok=True)

    async def delete(self, skill_id: str) -> None:
        """Delete the Skill document, if present."""
        if not is_skill_id(skill_id):
            raise SkillSourceError("invalid Skill ID for filesystem deletion")
        path = self._paths.pop(skill_id, self._root / f"{skill_id}.yaml")
        try:
            await asyncio.to_thread(self._delete_sync, path)
        except OSError as error:
            raise SkillSourceError(f"cannot delete Skill {skill_id!r}") from error

    def _delete_sync(self, path: Path) -> None:
        if path.exists() or path.is_symlink():
            self._safe(path).unlink()


__all__ = ["FilesystemSkillSource", "SkillSource", "validate_source_id"]
