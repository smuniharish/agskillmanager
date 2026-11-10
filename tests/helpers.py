"""Skill factories and ABC-based fakes shared by the test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_capability_router import (
    Capability,
    CapabilityFilter,
    CapabilityType,
    Embedder,
    MCPRuntime,
)

from skill_manager import (
    Skill,
    SkillCapability,
    SkillDependency,
    SkillGenerationRequest,
    SkillGenerator,
    SkillLifecycle,
    SkillLifecycleState,
    SkillMetadata,
    SkillObservabilityEvent,
    SkillObservabilitySink,
    SkillOrigin,
    SkillProvenance,
    SkillSource,
    dump_skill_yaml,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def make_skill(
    name: str = "summarize-ticket",
    version: str = "1.0.0",
    *,
    description: str | None = None,
    instructions: Sequence[str] = (),
    dependencies: Sequence[SkillDependency] = (),
    capabilities: Sequence[str] = (),
    tags: Sequence[str] = (),
    prompts: Mapping[str, str] | None = None,
    state: SkillLifecycleState = SkillLifecycleState.ACTIVE,
    origin: SkillOrigin = SkillOrigin.HUMAN,
    **values: Any,
) -> Skill:
    return Skill(
        metadata=SkillMetadata(
            name=name,
            version=version,
            description=description or f"{name.replace('-', ' ').capitalize()}.",
            tags=tuple(tags),
        ),
        instructions=tuple(instructions) or (f"Apply the {name} procedure.",),
        dependencies=tuple(dependencies),
        capabilities=tuple(SkillCapability(name=item) for item in capabilities),
        prompts=dict(prompts or {}),
        lifecycle=SkillLifecycle(state=state),
        provenance=SkillProvenance(origin=origin),
        **values,
    )


def capability(name: str, capability_id: str | None = None) -> Capability:
    return Capability(
        capability_id=capability_id or f"tools:{name}",
        server_id="tools",
        type=CapabilityType.TOOL,
        name=name,
    )


class MemorySource(SkillSource):
    """A dictionary-backed source whose operations can be made to fail."""

    def __init__(
        self, source_id: str = "memory", *, documents: Mapping[str, str] | None = None
    ) -> None:
        self._source_id = source_id
        self.documents: dict[str, str] = dict(documents or {})
        self.fail_load: Exception | None = None
        self.fail_save: Exception | None = None
        self.fail_delete: Exception | None = None
        self.closed = False

    @property
    def source_id(self) -> str:
        return self._source_id

    async def load(self) -> Mapping[str, str]:
        if self.fail_load is not None:
            raise self.fail_load
        return dict(self.documents)

    async def save(self, skill: Skill) -> None:
        if self.fail_save is not None:
            raise self.fail_save
        self.documents[skill.skill_id] = dump_skill_yaml(skill)

    async def delete(self, skill_id: str) -> None:
        if self.fail_delete is not None:
            raise self.fail_delete
        self.documents.pop(skill_id, None)

    async def aclose(self) -> None:
        self.closed = True


class RecordingSink(SkillObservabilitySink):
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[SkillObservabilityEvent] = []
        self.fail = fail

    async def emit(self, event: SkillObservabilityEvent) -> None:
        if self.fail:
            raise RuntimeError("sink unavailable")
        self.events.append(event)

    def names(self) -> list[str]:
        return [event.name for event in self.events]


class StaticGenerator(SkillGenerator):
    """Return a fixed Skill and remember every request."""

    def __init__(self, skill: Skill) -> None:
        self.skill = skill
        self.requests: list[SkillGenerationRequest] = []

    async def generate(self, request: SkillGenerationRequest) -> Skill:
        self.requests.append(request)
        return self.skill


class KeywordEmbedder(Embedder):
    """Embed text as counts of a fixed vocabulary, so similarity is predictable."""

    def __init__(self, vocabulary: Sequence[str] = ("ticket", "invoice", "deploy")) -> None:
        self.vocabulary = tuple(vocabulary)

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(word)) for word in self.vocabulary]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class StaticMCPRuntime(MCPRuntime):
    """An MCPRuntime whose retrieval returns a fixed capability list."""

    def __init__(self, capabilities: Sequence[Capability] = (), *, error: Exception | None = None):
        super().__init__()
        self.capabilities = list(capabilities)
        self.error = error
        self.queries: list[str] = []
        self.limits: list[int] = []

    async def retrieve(
        self,
        query: str,
        *,
        type: CapabilityType | None = None,
        server_id: str | None = None,
        limit: int = 20,
        where: CapabilityFilter | None = None,
        include_unhealthy: bool = False,
    ) -> list[Capability]:
        self.limits.append(limit)
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.capabilities
