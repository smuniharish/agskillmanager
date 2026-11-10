"""Shared sample data and environment-configured model connections."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from skill_manager import Skill, SkillGenerationRequest, SkillGenerator, SkillMetadata

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from langchain_openai import ChatOpenAI


def sample_skill(name: str = "summarize-ticket", **values: Any) -> Skill:
    return Skill(
        metadata=SkillMetadata(
            name=name, version="1.0.0", description=f"Apply the {name} procedure."
        ),
        instructions=("Use only the supplied facts.", "Remove personal information."),
        **values,
    )


class SampleGenerator(SkillGenerator):
    async def generate(self, request: SkillGenerationRequest) -> Skill:
        return sample_skill()


@asynccontextmanager
async def chat_model() -> AsyncGenerator[ChatOpenAI, None]:
    import openai
    from langchain_openai import ChatOpenAI

    key = os.getenv("EXPLABS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise SystemExit("Set EXPLABS_API_KEY or OPENAI_API_KEY before running this example.")
    base_url = os.getenv("OPENAI_BASE_URL")
    if os.getenv("EXPLABS_API_KEY") and not base_url:
        base_url = "https://api.experientiallabs.ai/v1"
    model = os.getenv(
        "OPENAI_MODEL", "gpt-5.6-luna" if os.getenv("EXPLABS_API_KEY") else "gpt-4o-mini"
    )
    async with openai.DefaultAsyncHttpxClient() as client:
        yield ChatOpenAI(
            model=model,
            api_key=key,
            base_url=base_url,
            http_async_client=client,
            timeout=120,
            max_retries=2,
        )


def show(title: str, payload: Any) -> None:
    print(f"\n--- {title} ---")
    print(json.dumps(payload, indent=2, default=str))
