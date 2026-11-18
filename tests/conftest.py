from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from retrievalloom import RetrievalEngine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture(autouse=True)
async def close_retrieval_engines(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Close engines a test left open, so unclosed SQLite handles never warn later.

    Only engines opened on the test's own event loop are closed here; engines opened
    by another loop (for example an app's private runner) belong to that loop's owner.
    """
    loop = asyncio.get_running_loop()
    opened: list[RetrievalEngine] = []
    initialize = RetrievalEngine.initialize

    async def tracked(self: RetrievalEngine) -> None:
        if asyncio.get_running_loop() is loop:
            opened.append(self)
        await initialize(self)

    monkeypatch.setattr(RetrievalEngine, "initialize", tracked)
    yield
    for engine in opened:
        if engine.state.value != "closed":
            await engine.close()
