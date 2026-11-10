"""Composable retrieval and reranking for bounded Skill discovery."""

from __future__ import annotations

import asyncio
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from skill_manager.errors import SkillDiscoveryError
from skill_manager.models import Skill, SkillLifecycleState

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mcp_capability_router import Embedder

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.]*", re.IGNORECASE)
_FILTER_KEYS = frozenset({"name", "version", "tag", "capability"})


@dataclass(frozen=True, slots=True)
class RetrievedSkill:
    """A retrieved Skill candidate and its backend-specific relevance score."""

    skill: Skill
    score: float


class SkillRetriever(ABC):
    """Extension point that indexes Skills and returns scored candidates.

    `PipelineDiscoveryProvider` calls `index` whenever the catalog changes and
    `retrieve` for each query. Return only ``ACTIVE`` Skills that satisfy
    ``filters``; use `matches_filters` to apply them.
    """

    @abstractmethod
    async def index(self, skills: Sequence[Skill]) -> None:
        """Replace the retriever's catalog snapshot."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedSkill]:
        """Return at most ``limit`` active, filtered candidates."""


class SkillReranker(ABC):
    """Extension point that orders retrieved candidates into the final result."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedSkill],
        *,
        top_k: int,
    ) -> list[Skill]:
        """Return at most ``top_k`` of ``candidates`` in final relevance order."""


class DiscoveryProvider(ABC):
    """Extension point for indexed, bounded Skill discovery.

    `SkillManager` keeps the provider's index in sync with the catalog and calls
    `discover` from `SkillManager.discover`.
    """

    @abstractmethod
    async def index(self, skills: Sequence[Skill]) -> None:
        """Replace the discoverable catalog snapshot."""

    @abstractmethod
    async def discover(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Skill]:
        """Return at most ``top_k`` active candidates."""


def validate_filters(filters: Mapping[str, Any] | None) -> None:
    """Raise `SkillDiscoveryError` when ``filters`` uses an unsupported key.

    Supported keys are ``name``, ``version``, ``tag`` and ``capability``.
    """
    if filters:
        unknown = sorted(set(filters) - _FILTER_KEYS)
        if unknown:
            raise SkillDiscoveryError(f"unsupported Skill discovery filters: {unknown}")


def matches_filters(skill: Skill, filters: Mapping[str, Any] | None) -> bool:
    """Return whether ``skill`` is ``ACTIVE`` and satisfies every filter."""
    if skill.lifecycle.state is not SkillLifecycleState.ACTIVE:
        return False
    if not filters:
        return True
    checks = {
        "name": lambda expected: skill.metadata.name == expected,
        "version": lambda expected: skill.metadata.version == expected,
        "tag": lambda expected: expected in skill.metadata.tags,
        "capability": lambda expected: any(item.name == expected for item in skill.capabilities),
    }
    return all(checks[key](expected) for key, expected in filters.items())


def skill_document(skill: Skill) -> str:
    """Return the text that retrievers index for ``skill``."""
    return "\n".join(
        (
            skill.metadata.name,
            skill.metadata.description,
            " ".join(skill.metadata.tags),
            "\n".join(skill.instructions),
            " ".join(capability.name for capability in skill.capabilities),
        )
    )


def _active(skills: Sequence[Skill]) -> tuple[Skill, ...]:
    return tuple(skill for skill in skills if skill.lifecycle.state is SkillLifecycleState.ACTIVE)


def _check_limit(limit: int) -> None:
    if limit < 1:
        raise SkillDiscoveryError("retrieval limit must be at least 1")


def _top(retrieved: list[RetrievedSkill], limit: int) -> list[RetrievedSkill]:
    retrieved.sort(key=lambda item: (-item.score, item.skill.skill_id))
    return retrieved[:limit]


class LexicalSkillRetriever(SkillRetriever):
    """Deterministic inverted-index retrieval over Skill text.

    The score is the number of distinct query terms found in a Skill. An empty
    query matches every active Skill with score zero.
    """

    def __init__(self) -> None:
        self._skills: tuple[Skill, ...] = ()
        self._tokens: dict[str, frozenset[str]] = {}
        self._postings: dict[str, frozenset[str]] = {}

    async def index(self, skills: Sequence[Skill]) -> None:
        """Tokenize every active Skill and rebuild the inverted index."""
        active = _active(skills)
        tokens = {
            skill.skill_id: frozenset(_TOKEN_PATTERN.findall(skill_document(skill).lower()))
            for skill in active
        }
        postings: dict[str, set[str]] = {}
        for skill_id, skill_tokens in tokens.items():
            for token in skill_tokens:
                postings.setdefault(token, set()).add(skill_id)
        self._skills = active
        self._tokens = tokens
        self._postings = {token: frozenset(ids) for token, ids in postings.items()}

    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedSkill]:
        """Return the active Skills sharing the most terms with ``query``."""
        _check_limit(limit)
        validate_filters(filters)
        terms = frozenset(_TOKEN_PATTERN.findall(query.lower()))
        if terms:
            ids = frozenset().union(*(self._postings.get(term, frozenset()) for term in terms))
            candidates = [skill for skill in self._skills if skill.skill_id in ids]
        else:
            candidates = list(self._skills)
        return _top(
            [
                RetrievedSkill(skill, float(len(terms & self._tokens[skill.skill_id])))
                for skill in candidates
                if matches_filters(skill, filters)
            ],
            limit,
        )


def _unit(vector: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(math.fsum(value * value for value in vector))
    return tuple(value / norm for value in vector) if norm else tuple(0.0 for _ in vector)


class SemanticSkillRetriever(SkillRetriever):
    """Dense cosine-similarity retrieval backed by an injected `Embedder`.

    Any `mcp_capability_router.Embedder` works. With the ``langchain`` extra,
    `skill_manager.integrations.langchain.LangChainEmbedder` adapts every
    LangChain ``Embeddings``.
    """

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._entries: tuple[tuple[Skill, tuple[float, ...]], ...] = ()
        self._index_lock = asyncio.Lock()

    async def index(self, skills: Sequence[Skill]) -> None:
        """Embed every active Skill and store unit-length vectors."""
        active = _active(skills)
        try:
            vectors = await self._embedder.embed_documents([skill_document(s) for s in active])
        except Exception as error:
            raise SkillDiscoveryError("semantic Skill index embedding failed") from error
        if len(vectors) != len(active):
            raise SkillDiscoveryError("embedder returned a different number of vectors")
        async with self._index_lock:
            self._entries = tuple(
                (skill, _unit(vector)) for skill, vector in zip(active, vectors, strict=True)
            )

    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedSkill]:
        """Return the active Skills closest to ``query`` by cosine similarity."""
        _check_limit(limit)
        validate_filters(filters)
        async with self._index_lock:
            entries = self._entries
        try:
            query_vector = _unit(await self._embedder.embed_query(query))
        except Exception as error:
            raise SkillDiscoveryError("semantic Skill query embedding failed") from error
        try:
            return _top(
                [
                    RetrievedSkill(
                        skill,
                        math.fsum(a * b for a, b in zip(query_vector, vector, strict=True)),
                    )
                    for skill, vector in entries
                    if matches_filters(skill, filters)
                ],
                limit,
            )
        except ValueError as error:
            raise SkillDiscoveryError("query and index vectors differ in dimension") from error


class ScoreSkillReranker(SkillReranker):
    """Order candidates by retrieval score, breaking ties by Skill ID."""

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedSkill],
        *,
        top_k: int,
    ) -> list[Skill]:
        """Return the ``top_k`` highest-scoring Skills."""
        del query
        return [item.skill for item in _top(list(candidates), top_k)]


class PipelineDiscoveryProvider(DiscoveryProvider):
    """Compose a retriever and a reranker into bounded, verified discovery.

    The provider asks the retriever for ``max(top_k, candidate_pool_size)``
    candidates, reranks them, and checks that neither stage exceeded its limit,
    invented a Skill, or returned an inactive or filtered-out Skill.

    Args:
        retriever: Candidate source; defaults to `LexicalSkillRetriever`.
        reranker: Final ordering; defaults to `ScoreSkillReranker`.
        candidate_pool_size: Minimum number of candidates to rerank.
    """

    def __init__(
        self,
        retriever: SkillRetriever | None = None,
        *,
        reranker: SkillReranker | None = None,
        candidate_pool_size: int = 50,
    ) -> None:
        if candidate_pool_size < 1:
            raise ValueError("candidate_pool_size must be at least 1")
        self._retriever = retriever if retriever is not None else LexicalSkillRetriever()
        self._reranker = reranker if reranker is not None else ScoreSkillReranker()
        self._candidate_pool_size = candidate_pool_size

    async def index(self, skills: Sequence[Skill]) -> None:
        """Forward the catalog snapshot to the retriever."""
        await self._retriever.index(skills)

    async def discover(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Skill]:
        """Retrieve, rerank and verify at most ``top_k`` Skills."""
        if top_k < 1:
            raise SkillDiscoveryError("top_k must be at least 1")
        validate_filters(filters)
        limit = max(top_k, self._candidate_pool_size)
        candidates = await self._retriever.retrieve(query, limit=limit, filters=filters)
        if len(candidates) > limit:
            raise SkillDiscoveryError("Skill retriever returned more than its candidate limit")
        allowed = tuple(item for item in candidates if matches_filters(item.skill, filters))
        ranked = await self._reranker.rerank(query, allowed, top_k=top_k)
        if len(ranked) > top_k:
            raise SkillDiscoveryError("Skill reranker returned more than top_k candidates")
        by_id = {item.skill.skill_id: item.skill for item in allowed}
        if len({skill.skill_id for skill in ranked}) != len(ranked) or any(
            by_id.get(skill.skill_id) != skill for skill in ranked
        ):
            raise SkillDiscoveryError("Skill reranker returned an invalid candidate set")
        return ranked


__all__ = [
    "DiscoveryProvider",
    "LexicalSkillRetriever",
    "PipelineDiscoveryProvider",
    "RetrievedSkill",
    "ScoreSkillReranker",
    "SemanticSkillRetriever",
    "SkillReranker",
    "SkillRetriever",
    "matches_filters",
    "skill_document",
    "validate_filters",
]
