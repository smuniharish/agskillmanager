from __future__ import annotations

import os
from pathlib import Path

import pytest

from skill_manager import FilesystemSkillSource, SkillSourceError, dump_skill_yaml, parse_skill_yaml
from skill_manager import sources as sources_module
from skill_manager.sources import SkillSource, validate_source_id
from skill_manager.testing import SkillSourceContract
from tests.helpers import make_skill


class TestFilesystemSkillSource(SkillSourceContract):
    @pytest.fixture(autouse=True)
    def _root(self, tmp_path: Path) -> None:
        self.root = tmp_path / "skills"

    async def make_source(self) -> SkillSource:
        return FilesystemSkillSource(self.root)


def test_source_ids_are_validated() -> None:
    assert validate_source_id("primary") == "primary"
    for bad in ("", "  ", "a\nb", "x" * 129):
        with pytest.raises(ValueError, match="source_id"):
            validate_source_id(bad)


async def test_missing_root_loads_nothing_and_root_is_resolved(tmp_path: Path) -> None:
    source = FilesystemSkillSource(tmp_path / "absent", source_id="docs")
    assert await source.load() == {}
    assert source.root == (tmp_path / "absent").resolve()
    assert source.source_id == "docs"


async def test_root_must_be_a_directory(tmp_path: Path) -> None:
    file = tmp_path / "file"
    file.write_text("x", encoding="utf-8")
    with pytest.raises(SkillSourceError, match="not a directory"):
        await FilesystemSkillSource(file).load()


async def test_existing_files_are_rewritten_in_place(tmp_path: Path) -> None:
    skill = make_skill()
    (tmp_path / "custom-name.yml").write_text(dump_skill_yaml(skill), encoding="utf-8")
    (tmp_path / "notes.yaml").write_text("title: no skill id", encoding="utf-8")
    source = FilesystemSkillSource(tmp_path)
    assert set(await source.load()) == {"custom-name.yml", "notes.yaml"}
    updated = skill.model_copy(update={"revision": 2})
    await source.save(updated)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["custom-name.yml", "notes.yaml"]
    text = (tmp_path / "custom-name.yml").read_text(encoding="utf-8")
    assert await parse_skill_yaml(text) == updated
    await source.delete(skill.skill_id)
    assert [path.name for path in tmp_path.iterdir()] == ["notes.yaml"]


async def test_delete_requires_a_skill_id(tmp_path: Path) -> None:
    with pytest.raises(SkillSourceError, match="invalid Skill ID"):
        await FilesystemSkillSource(tmp_path).delete("../escape")


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("creating symbolic links is not permitted on this machine")


def test_path_guards_without_symlink_privileges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = FilesystemSkillSource(tmp_path / "root")
    outside = tmp_path / "outside.yaml"
    with pytest.raises(SkillSourceError, match="escapes"):
        source._safe(outside)
    candidate = source.root / "linked.yaml"
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == candidate)
    with pytest.raises(SkillSourceError, match="symbolic links"):
        source._safe(candidate)


async def test_symbolic_links_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "outside.yaml"
    skill = make_skill()
    target.write_text(dump_skill_yaml(skill), encoding="utf-8")
    _symlink(root / f"{skill.skill_id}.yaml", target)
    source = FilesystemSkillSource(root)
    with pytest.raises(SkillSourceError, match="symbolic links"):
        await source.load()
    with pytest.raises(SkillSourceError, match="symbolic links"):
        await source.save(skill)
    with pytest.raises(SkillSourceError, match="symbolic links"):
        await source.delete(skill.skill_id)


async def test_paths_escaping_the_root_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink(root, outside)
    (outside / "a.yaml").write_text("skill_id: x", encoding="utf-8")
    source = FilesystemSkillSource(tmp_path / "root")
    source._root = root.absolute()  # the configured root no longer resolves to itself
    with pytest.raises(SkillSourceError, match="escapes"):
        await source.load()


async def test_os_errors_become_source_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = FilesystemSkillSource(tmp_path)
    skill = make_skill()
    await source.save(skill)

    def fail(*args: object, **kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", fail)
    with pytest.raises(SkillSourceError, match="cannot load"):
        await source.load()
    with monkeypatch.context() as patch:
        patch.setattr(sources_module, "NamedTemporaryFile", fail)
        with pytest.raises(SkillSourceError, match="cannot persist"):
            await source.save(skill)
    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(SkillSourceError, match="cannot persist"):
        await source.save(skill)
    assert not [path for path in tmp_path.iterdir() if path.suffix == ".tmp"]
    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(SkillSourceError, match="cannot delete"):
        await source.delete(skill.skill_id)
