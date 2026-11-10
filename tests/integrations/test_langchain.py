from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.runnables import RunnableLambda
from xstructured import XStructuredError

from skill_manager import (
    Skill,
    SkillFeedback,
    SkillGenerationError,
    SkillGenerationRequest,
)
from skill_manager.integrations.langchain import XStructuredSkillGenerator
from tests.helpers import make_skill

DRAFT_FIELDS = {"metadata", "instructions", "dependencies", "capabilities", "resources", "prompts"}


def draft_json(skill: Skill) -> str:
    return skill.model_dump_json(include=DRAFT_FIELDS)


async def test_generation_and_revision_inputs() -> None:
    skill = make_skill()
    generator = XStructuredSkillGenerator(
        RunnableLambda(lambda _: f"<xstructured>{draft_json(skill)}</xstructured>")
    )
    assert generator.name == "xstructured"
    generated = await generator.generate(SkillGenerationRequest(input="write a skill"))
    assert generated.model_dump(include=DRAFT_FIELDS) == skill.model_dump(include=DRAFT_FIELDS)
    assert generated.skill_id != skill.skill_id
    feedback = SkillFeedback(
        feedback_id="review",
        payload={"feedback": "make it safer"},
        metadata={"reviewer": "test"},
        created_at=datetime.now(UTC),
    )
    for value in ("revise", {"task": "revise"}):
        request = SkillGenerationRequest(input=value, parent=skill, feedback=(feedback,))
        enriched = generator._input(request)
        if isinstance(enriched, dict):
            assert enriched["parent_skill"]["skill_id"] == skill.skill_id
            assert enriched["previous_skill_feedback"][0]["feedback"] == dict(feedback.payload)
        else:
            assert "Reviewer feedback" in enriched
            assert "make it safer" in enriched


async def test_model_authored_identity_and_invalid_skills_are_refused() -> None:
    skill = make_skill()
    for answer in (
        skill.model_dump_json(),
        draft_json(skill).replace('"instructions":[', '"instructions":["   ",'),
    ):
        generator = XStructuredSkillGenerator(
            RunnableLambda(lambda _, answer=answer: f"<xstructured>{answer}</xstructured>")
        )
        with pytest.raises(SkillGenerationError, match="could not extract"):
            await generator.generate(SkillGenerationRequest(input="x"))


async def test_invalid_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = XStructuredSkillGenerator(RunnableLambda(lambda _: ""))
    monkeypatch.setattr(
        generator,
        "_structured",
        SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(structured=None))),
    )
    with pytest.raises(SkillGenerationError, match="not a valid Skill"):
        await generator.generate(SkillGenerationRequest(input="x"))
    generator._structured.ainvoke.side_effect = XStructuredError("invalid")
    with pytest.raises(SkillGenerationError, match="could not extract"):
        await generator.generate(SkillGenerationRequest(input="x"))
