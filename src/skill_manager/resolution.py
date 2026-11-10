"""Deterministic dependency resolution and SkillBundle composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from skill_manager.errors import (
    SkillConflictError,
    SkillDependencyCycleError,
    SkillDependencyError,
)
from skill_manager.models import Skill, SkillDependency, SkillLifecycleState

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class _Requirement:
    parent: Skill
    dependency: SkillDependency
    path: tuple[str, ...]


def resolve_dependencies(roots: Iterable[Skill], catalog: Iterable[Skill]) -> tuple[Skill, ...]:
    """Resolve the transitive dependencies of ``roots`` against the active ``catalog``.

    The search prefers the highest matching version of each dependency and
    backtracks when a later constraint rules it out. One revision is chosen per
    Skill name, shared by every Skill that depends on it.

    Returns:
        The selected Skills in dependency-first order, ties broken by name,
        version and Skill ID, so equal inputs always produce equal output.

    Raises:
        SkillDependencyError: If a dependency has no matching active revision.
        SkillDependencyCycleError: If the selected Skills form a cycle.
        SkillConflictError: If two roots share a name or constraints conflict.
    """
    available = tuple(
        skill for skill in catalog if skill.lifecycle.state is SkillLifecycleState.ACTIVE
    )
    sorted_roots = tuple(
        sorted(
            roots,
            key=lambda item: (item.metadata.name, Version(item.metadata.version), item.skill_id),
        )
    )
    assignments: dict[str, Skill] = {}
    for root in sorted_roots:
        existing = assignments.get(root.metadata.name)
        if existing is not None and existing.skill_id != root.skill_id:
            raise SkillConflictError(
                f"multiple root revisions selected for Skill {root.metadata.name!r}"
            )
        assignments[root.metadata.name] = root

    def matching(dependency: SkillDependency) -> list[Skill]:
        spec = SpecifierSet("" if dependency.version == "*" else dependency.version)
        matches = [
            skill
            for skill in available
            if skill.metadata.name == dependency.name and Version(skill.metadata.version) in spec
        ]
        return sorted(
            matches,
            key=lambda item: (Version(item.metadata.version), item.skill_id),
            reverse=True,
        )

    def enqueue_children(
        skill: Skill,
        path: tuple[str, ...],
    ) -> tuple[_Requirement, ...]:
        return tuple(
            _Requirement(skill, dependency, path)
            for dependency in sorted(skill.dependencies, key=lambda item: item.name)
        )

    def topological_order(
        chosen: dict[str, Skill],
        edges: dict[str, set[str]],
    ) -> tuple[Skill, ...]:
        by_id = {skill.skill_id: skill for skill in chosen.values()}
        visiting: list[str] = []
        visited: set[str] = set()
        result: list[Skill] = []

        def visit(skill_id: str) -> None:
            if skill_id in visiting:
                start = visiting.index(skill_id)
                cycle_ids = (*visiting[start:], skill_id)
                raise SkillDependencyCycleError(
                    tuple(by_id[item].metadata.name for item in cycle_ids)
                )
            if skill_id in visited:
                return
            visiting.append(skill_id)
            skill = by_id[skill_id]
            children = sorted(
                edges.get(skill_id, set()),
                key=lambda item: (
                    by_id[item].metadata.name,
                    Version(by_id[item].metadata.version),
                    item,
                ),
            )
            for child_id in children:
                visit(child_id)
            visiting.pop()
            visited.add(skill_id)
            result.append(skill)

        for skill in sorted(
            by_id.values(),
            key=lambda item: (
                item.metadata.name,
                Version(item.metadata.version),
                item.skill_id,
            ),
        ):
            visit(skill.skill_id)
        return tuple(result)

    def search(
        pending: tuple[_Requirement, ...],
        chosen: dict[str, Skill],
        edges: dict[str, set[str]],
    ) -> tuple[Skill, ...]:
        if not pending:
            return topological_order(chosen, edges)

        requirement, remaining = pending[0], pending[1:]
        dependency = requirement.dependency
        path = (*requirement.path, requirement.parent.metadata.name, dependency.name)
        options = matching(dependency)
        if not options:
            raise SkillDependencyError(
                "missing dependency along path "
                + " -> ".join(path)
                + f" (requires {dependency.version})"
            )

        selected = chosen.get(dependency.name)
        if selected is not None:
            spec = SpecifierSet("" if dependency.version == "*" else dependency.version)
            if Version(selected.metadata.version) not in spec:
                raise SkillConflictError(
                    "conflicting dependency constraints along path " + " -> ".join(path)
                )
            next_edges = {key: set(value) for key, value in edges.items()}
            next_edges.setdefault(requirement.parent.skill_id, set()).add(selected.skill_id)
            return search(remaining, chosen, next_edges)

        failures: list[SkillDependencyError | SkillConflictError] = []
        for candidate in options:
            next_chosen = dict(chosen)
            next_chosen[dependency.name] = candidate
            next_edges = {key: set(value) for key, value in edges.items()}
            next_edges.setdefault(requirement.parent.skill_id, set()).add(candidate.skill_id)
            next_pending = (
                *enqueue_children(
                    candidate,
                    (*requirement.path, requirement.parent.metadata.name),
                ),
                *remaining,
            )
            try:
                return search(next_pending, next_chosen, next_edges)
            except (SkillDependencyError, SkillConflictError) as error:
                failures.append(error)
        raise failures[0]

    pending = tuple(
        requirement for root in sorted_roots for requirement in enqueue_children(root, ())
    )
    initial_edges = {root.skill_id: set() for root in sorted_roots}
    return search(
        pending,
        assignments,
        initial_edges,
    )
