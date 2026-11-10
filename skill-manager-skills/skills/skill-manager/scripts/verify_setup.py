"""Verify core and optionally selected extras without external services."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json

from skill_manager import Skill, SkillManager, SkillMetadata, __version__


async def verify() -> None:
    async with SkillManager() as manager:
        skill = await manager.register_skill(
            Skill(
                metadata=SkillMetadata(
                    name="setup-check", version="1.0.0", description="Verify setup."
                ),
                instructions=("Return a validated bundle.",),
            )
        )
        bundle = await manager.build_bundle([skill])
        assert bundle.dependency_order == (skill.skill_id,)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for extra in ("langchain", "postgres", "otel"):
        parser.add_argument(f"--{extra}", action="store_true")
    args = parser.parse_args()
    for extra in ("langchain", "postgres", "otel"):
        if getattr(args, extra):
            module = (
                "skill_manager.integrations.langchain"
                if extra == "langchain"
                else f"skill_manager.{extra}"
            )
            importlib.import_module(module)
    asyncio.run(verify())
    print(json.dumps({"ok": True, "version": __version__}))


if __name__ == "__main__":
    main()
