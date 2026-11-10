from __future__ import annotations

import importlib
import os
import runpy
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from tests.helpers import make_skill
from tests.integrations.test_langchain import DRAFT_FIELDS

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
pytestmark = pytest.mark.examples
OFFLINE = {
    "quickstart.py": ['"privacy"', '"summarize-ticket"'],
    "filesystem_source.py": ["Reloaded catalog", "summarize-ticket"],
    "approval_workflow.py": ['"revision": 2', '"state": "ACTIVE"'],
    "semantic_discovery.py": ['"explain-invoice"'],
    "langchain_embeddings.py": ["LangChain embeddings", "summarize-ticket"],
    "custom_framework.py": ["Plain Python agent context", "Remove personal information"],
    "refresh.py": ["Catalog refreshed", "Refresh status"],
    "xai_decisions.py": ["Decision explanation", "generate_skill", "build_bundle"],
    "customization_matrix.py": ["Injected collaborators", "skill.approved"],
}
LLM = {
    "llm_skill_generation.py": "Generated review candidate",
    "langgraph_agent.py": "LangGraph answer",
    "create_agent.py": "LangChain agent answer",
    "deepagents_agent.py": "Deep agent answer",
}
SERVICES = {
    "postgres_catalog.py": ("SKILL_MANAGER_POSTGRES_DSN", "PostgreSQL catalog"),
    "mcp_capabilities.py": ("SKILL_MANAGER_MCP_URL", "Resolved MCP capabilities"),
    "otel_observability.py": ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTel export complete"),
}


def run_example(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(EXAMPLES))
    runpy.run_path(str(EXAMPLES / name), run_name="__main__")


@pytest.mark.parametrize(("name", "expected"), OFFLINE.items())
def test_offline_examples(
    name: str,
    expected: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_example(name, monkeypatch)
    output = capsys.readouterr().out
    assert all(text in output for text in expected)


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        return self


@pytest.mark.parametrize(("name", "expected"), LLM.items())
def test_llm_examples_with_scripted_model(
    name: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.syspath_prepend(str(EXAMPLES))
    shared = importlib.import_module("_shared")
    answer = (
        f"<xstructured>{make_skill().model_dump_json(include=DRAFT_FIELDS)}</xstructured>"
        if name == "llm_skill_generation.py"
        else "Ticket #42 needs a password reset."
    )

    @asynccontextmanager
    async def chat_model() -> AsyncGenerator[ScriptedModel, None]:
        yield ScriptedModel(messages=iter([AIMessage(content=answer)]))

    monkeypatch.setattr(shared, "chat_model", chat_model)
    run_example(name, monkeypatch)
    assert expected in capsys.readouterr().out


@pytest.mark.live
@pytest.mark.parametrize(("name", "expected"), LLM.items())
def test_live_llm(name: str, expected: str) -> None:
    if not (os.getenv("EXPLABS_API_KEY") or os.getenv("OPENAI_API_KEY")):
        pytest.skip("set EXPLABS_API_KEY or OPENAI_API_KEY")
    result = subprocess.run(  # noqa: S603 - fixed repository example paths
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    assert expected in result.stdout


@pytest.mark.live
@pytest.mark.parametrize(("name", "settings"), SERVICES.items())
def test_live_service(name: str, settings: tuple[str, str]) -> None:
    variable, expected = settings
    if not os.getenv(variable):
        pytest.skip(f"set {variable}")
    result = subprocess.run(  # noqa: S603 - fixed repository example paths
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert expected in result.stdout


def test_streamlit_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("SKILL_MANAGER_UI_SKILLS_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(EXAMPLES))
    app = AppTest.from_file(str(EXAMPLES / "streamlit_catalog.py")).run()
    assert not app.exception
    assert app.metric[0].value == "0"
    app.text_input(key="register-name").set_value("manual-review")
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[0].value == "1"
    app.button[1].click().run()
    assert not app.exception
    assert app.metric[1].value == "1"
    next(button for button in app.button if button.label == "Reject").click().run()
    assert not app.exception
    assert app.metric[1].value == "0"
    next(
        button for button in app.button if button.label == "Regenerate from feedback"
    ).click().run()
    assert not app.exception
    assert app.metric[1].value == "1"
    next(button for button in app.button if button.label == "Approve").click().run()
    assert not app.exception
    assert app.metric[1].value == "0"
    app.session_state["dashboard"].close()


def test_every_example_has_coverage() -> None:
    scripts = {path.name for path in EXAMPLES.glob("*.py") if not path.name.startswith("_")}
    assert scripts == set(OFFLINE) | set(LLM) | set(SERVICES) | {
        "streamlit_catalog.py",
        "local_mcp_server.py",
    }
