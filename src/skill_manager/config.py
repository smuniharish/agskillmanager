"""Immutable Skill Manager policy and limit configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SkillManagerConfig(BaseModel):
    """Policy switches and resource limits for one `SkillManager`.

    Attributes:
        allow_agent_skill_creation: Accept agent-generated Skills at all.
        require_human_approval: Hold agent-generated Skills in
            ``PENDING_APPROVAL`` until a reviewer approves them.
        max_document_bytes: Largest Skill YAML document a source may supply.
        capability_candidate_limit: Candidates requested from
            `MCPRuntime.retrieve` per required capability name.
        capability_cache_size: Resolved capabilities kept between bundle builds.
        feedback_context_limit: Rejection events passed to a `SkillGenerator`
            when it revises a parent Skill.
        error_history_size: Observability and XAI failures retained on
            `SkillManager.observability_errors`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allow_agent_skill_creation: bool = True
    require_human_approval: bool = False
    max_document_bytes: int = Field(default=1_000_000, ge=1)
    capability_candidate_limit: int = Field(default=50, ge=1)
    capability_cache_size: int = Field(default=1024, ge=0)
    feedback_context_limit: int = Field(default=20, ge=0)
    error_history_size: int = Field(default=100, ge=1)
