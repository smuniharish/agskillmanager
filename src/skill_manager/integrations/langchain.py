"""LangChain integration: xstructured Skill generation and embeddings.

Install with ``pip install 'agskillmanager[langchain]'``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import Field, model_validator
from retrievalloom.contracts.component import ComponentInfo, make_info
from retrievalloom.contracts.models import EmbeddingModelABC

from skill_manager._optional import optional_import
from skill_manager.errors import SkillGenerationError
from skill_manager.generation import SkillGenerationRequest, SkillGenerator
from skill_manager.models import (
    FrozenModel,
    Skill,
    SkillCapability,
    SkillDependency,
    SkillMetadata,
    SkillReference,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.embeddings import Embeddings
    from langchain_core.runnables import Runnable

_xstructured = optional_import("xstructured", "langchain")


class LangChainEmbeddingModel(EmbeddingModelABC):
    """Adapt any LangChain ``Embeddings`` to a RetrievalLoom embedding model.

    Pass it as ``Components(embedding=...)`` to `RetrievalLoomDiscoveryProvider`
    to add dense semantic search to Skill discovery. The adapter calls the
    asynchronous ``aembed_documents`` and ``aembed_query`` methods.

    Args:
        embeddings: The LangChain embeddings implementation.
        dimensions: Length of every vector the embeddings return.
        model_identity: Stable model name; changing it makes RetrievalLoom
            build a new vector index. Defaults to the embeddings class name.
    """

    def __init__(
        self,
        embeddings: Embeddings,
        *,
        dimensions: int,
        model_identity: str | None = None,
    ) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1")
        self._embeddings = embeddings
        self._dimensions = dimensions
        self._info = make_info(
            component="embedding",
            implementation="langchain",
            version="1",
            model_identity=model_identity or type(embeddings).__name__,
            dimensions=dimensions,
        )

    @property
    def info(self) -> ComponentInfo:
        """Return the component identity RetrievalLoom fingerprints."""
        return self._info

    @property
    def dimensions(self) -> int:
        """Return the vector length."""
        return self._dimensions

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed Skill documents."""
        return await self._embeddings.aembed_documents(list(texts))

    async def embed_query(self, text: str) -> Sequence[float]:
        """Embed a discovery query."""
        return await self._embeddings.aembed_query(text)


def _feedback_payload(request: SkillGenerationRequest) -> list[dict[str, Any]]:
    return [
        {
            "feedback": dict(item.payload),
            "metadata": dict(item.metadata),
            "created_at": item.created_at.isoformat(),
        }
        for item in request.feedback
    ]


class _SkillDraft(FrozenModel):
    """The model-authored part of a Skill.

    The ID, revision, provenance, lifecycle and governance belong to the
    manager, so the model is never asked to invent them.
    """

    metadata: SkillMetadata
    instructions: tuple[str, ...]
    dependencies: tuple[SkillDependency, ...] = ()
    capabilities: tuple[SkillCapability, ...] = ()
    resources: tuple[SkillReference, ...] = ()
    prompts: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_as_skill(self) -> _SkillDraft:
        """Apply every Skill rule, so xstructured repair sees the violations."""
        self.to_skill()
        return self

    def to_skill(self) -> Skill:
        """Return a new Skill revision built from the draft."""
        return Skill(**dict(self))


class XStructuredSkillGenerator(SkillGenerator):
    """Generate a Skill from any LangChain runnable through xstructured.

    xstructured injects the authorable Skill fields (metadata, instructions,
    dependencies, capabilities, resources and prompts) into the prompt,
    extracts and validates the JSON answer, and optionally repairs it with
    ``repair``. The manager assigns the ID, revision and governance.
    When the request revises a rejected parent, the parent Skill and the
    reviewer feedback are added to the input: as ``parent_skill`` and
    ``previous_skill_feedback`` keys for mapping inputs, or as appended text
    otherwise. Model and transport errors propagate unchanged.

    Args:
        runnable: The model or chain, for example ``ChatOpenAI(...)``.
        repair: Optional runnable that repairs invalid output.
        **options: Any other `xstructured.with_xstructured_output` option,
            such as ``parser_config``, ``repair_config`` or ``observer``.
    """

    def __init__(
        self,
        runnable: Runnable[Any, Any],
        *,
        repair: Runnable[Any, Any] | None = None,
        **options: Any,
    ) -> None:
        self._structured = _xstructured.with_xstructured_output(
            runnable, _SkillDraft, repair=repair, **options
        )

    @property
    def name(self) -> str:
        """Return ``xstructured``."""
        return "xstructured"

    async def generate(self, request: SkillGenerationRequest) -> Skill:
        """Run the structured runnable and return the extracted Skill."""
        try:
            result = await self._structured.ainvoke(self._input(request))
        except _xstructured.XStructuredError as error:
            raise SkillGenerationError("xstructured could not extract a valid Skill") from error
        if not isinstance(result.structured, _SkillDraft):
            raise SkillGenerationError("xstructured returned a value that is not a valid Skill")
        return result.structured.to_skill()

    @staticmethod
    def _input(request: SkillGenerationRequest) -> Any:
        if request.parent is None:
            return request.input
        parent = request.parent.model_dump(mode="json")
        feedback = _feedback_payload(request)
        if isinstance(request.input, Mapping):
            return {**request.input, "parent_skill": parent, "previous_skill_feedback": feedback}
        return (
            f"{request.input}\n\nRevise this rejected Skill:\n{json.dumps(parent)}"
            f"\n\nReviewer feedback:\n{json.dumps(feedback)}"
        )


__all__ = ["LangChainEmbeddingModel", "XStructuredSkillGenerator"]
