from __future__ import annotations

import json
import re
import runpy
from pathlib import Path

import pytest
from skills_ref import read_properties, validate

from skill_manager import SkillGenerationRequest, SkillSource
from skill_manager.testing import SkillSourceContract

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "agskillmanager-skills" / "skills"


@pytest.mark.parametrize("name", ["agskillmanager", "agskillmanager-extend"])
def test_skill_frontmatter_and_links(name: str) -> None:
    directory = SKILLS / name
    assert validate(directory) == []
    properties = read_properties(directory)
    assert properties.name == name
    text = (directory / "SKILL.md").read_text(encoding="utf-8")
    for link in re.findall(r"\]\((\./[^)#]+)\)", text):
        assert (directory / link).is_file()
    evals = json.loads((directory / "evals" / "evals.json").read_text(encoding="utf-8"))
    assert evals["skill_name"] == name
    assert all(item["prompt"] and item["expected_output"] for item in evals["evals"])


def test_setup_and_quickstart_scripts(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["verify_setup.py"])
    runpy.run_path(
        str(SKILLS / "agskillmanager" / "scripts" / "verify_setup.py"), run_name="__main__"
    )
    assert '"ok": true' in capsys.readouterr().out
    runpy.run_path(str(SKILLS / "agskillmanager" / "assets" / "quickstart.py"), run_name="__main__")
    assert "Remove personal information." in capsys.readouterr().out


def test_source_contract_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    directory = SKILLS / "agskillmanager-extend"
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_source.py",
            "source_template:MemorySkillSource",
            "--path",
            str(directory / "assets"),
        ],
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(directory / "scripts" / "check_source.py"), run_name="__main__")
    assert result.value.code == 0


async def test_generator_template() -> None:
    namespace = runpy.run_path(
        str(SKILLS / "agskillmanager-extend" / "assets" / "generator_template.py")
    )
    skill = await namespace["SupportSkillGenerator"]().generate(
        SkillGenerationRequest(input="review")
    )
    assert skill.metadata.name == "support-review"


class TestSourceTemplate(SkillSourceContract):
    async def make_source(self) -> SkillSource:
        namespace = runpy.run_path(
            str(SKILLS / "agskillmanager-extend" / "assets" / "source_template.py")
        )
        return namespace["MemorySkillSource"]()
