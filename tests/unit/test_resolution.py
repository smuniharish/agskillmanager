from __future__ import annotations

import pytest

from skill_manager import (
    SkillConflictError,
    SkillDependency,
    SkillDependencyCycleError,
    SkillDependencyError,
    SkillLifecycleState,
    resolve_dependencies,
)
from tests.helpers import make_skill


def names(skills: tuple) -> list[str]:
    return [f"{skill.metadata.name}@{skill.metadata.version}" for skill in skills]


def test_transitive_dependencies_are_ordered_dependency_first() -> None:
    base = make_skill("base")
    middle = make_skill("middle", dependencies=[SkillDependency(name="base")])
    root = make_skill("root", dependencies=[SkillDependency(name="middle")])
    assert names(resolve_dependencies([root], [base, middle, root])) == [
        "base@1.0.0",
        "middle@1.0.0",
        "root@1.0.0",
    ]


def test_highest_matching_active_version_is_selected() -> None:
    catalog = [
        make_skill("base", "1.2.0"),
        make_skill("base", "1.10.0"),
        make_skill("base", "2.0.0"),
        make_skill("base", "1.11.0", state=SkillLifecycleState.PENDING_APPROVAL),
    ]
    root = make_skill("root", dependencies=[SkillDependency(name="base", version="<2")])
    assert names(resolve_dependencies([root], catalog))[0] == "base@1.10.0"


def test_shared_dependency_is_selected_once() -> None:
    base = make_skill("base")
    left = make_skill("left", dependencies=[SkillDependency(name="base")])
    right = make_skill("right", dependencies=[SkillDependency(name="base")])
    root = make_skill(
        "root", dependencies=[SkillDependency(name="left"), SkillDependency(name="right")]
    )
    resolved = resolve_dependencies([root], [base, left, right, root])
    assert names(resolved).count("base@1.0.0") == 1


def test_root_that_is_also_a_dependency_is_reused() -> None:
    base = make_skill("base")
    root = make_skill("root", dependencies=[SkillDependency(name="base")])
    assert len(resolve_dependencies([root, base], [base, root])) == 2


def test_search_backtracks_to_an_older_version() -> None:
    shared_1 = make_skill("shared", "1.0.0")
    shared_2 = make_skill("shared", "2.0.0")
    new_lib = make_skill(
        "lib", "2.0.0", dependencies=[SkillDependency(name="shared", version=">=2")]
    )
    old_lib = make_skill(
        "lib", "1.0.0", dependencies=[SkillDependency(name="shared", version="<2")]
    )
    root = make_skill(
        "root",
        dependencies=[
            SkillDependency(name="lib"),
            SkillDependency(name="shared", version="<2"),
        ],
    )
    resolved = resolve_dependencies([root], [shared_1, shared_2, new_lib, old_lib, root])
    assert "lib@1.0.0" in names(resolved)
    assert "shared@1.0.0" in names(resolved)


def test_missing_dependency_names_the_path() -> None:
    root = make_skill("root", dependencies=[SkillDependency(name="ghost", version=">=1")])
    with pytest.raises(SkillDependencyError, match="root -> ghost"):
        resolve_dependencies([root], [root])


def test_conflicting_constraints_raise() -> None:
    base = make_skill("base", "1.0.0")
    root = make_skill(
        "root",
        dependencies=[SkillDependency(name="base"), SkillDependency(name="other")],
    )
    other = make_skill("other", dependencies=[SkillDependency(name="base", version=">=2")])
    with pytest.raises(SkillDependencyError):
        resolve_dependencies([root], [base, other, root])
    base_2 = make_skill("base", "2.0.0")
    pinned = make_skill("pinned", dependencies=[SkillDependency(name="base", version="<2")])
    root = make_skill(
        "root", dependencies=[SkillDependency(name="base"), SkillDependency(name="pinned")]
    )
    resolved = resolve_dependencies([root], [base, base_2, pinned, root])
    assert "base@1.0.0" in names(resolved)


def test_root_constraint_conflict_raises_conflict() -> None:
    base = make_skill("base", "1.0.0")
    root = make_skill("root", dependencies=[SkillDependency(name="base", version=">=2")])
    other = make_skill("base", "2.0.0")
    with pytest.raises(SkillConflictError, match="conflicting"):
        resolve_dependencies([root, base], [base, other, root])


def test_two_root_revisions_with_one_name_conflict() -> None:
    with pytest.raises(SkillConflictError, match="multiple root"):
        resolve_dependencies([make_skill("a", "1.0.0"), make_skill("a", "2.0.0")], [])


def test_cycles_are_reported() -> None:
    a = make_skill("a", dependencies=[SkillDependency(name="b")])
    b = make_skill("b", dependencies=[SkillDependency(name="a")])
    with pytest.raises(SkillDependencyCycleError) as caught:
        resolve_dependencies([a], [a, b])
    assert caught.value.path[0] == caught.value.path[-1]


def test_resolution_is_deterministic() -> None:
    skills = [make_skill(name) for name in ("c", "a", "b")]
    assert names(resolve_dependencies(skills, skills)) == ["a@1.0.0", "b@1.0.0", "c@1.0.0"]
