# Development and release

See [CONTRIBUTING](https://github.com/smuniharish/agskillmanager/blob/master/CONTRIBUTING.md),
[CHANGELOG](https://github.com/smuniharish/agskillmanager/blob/master/CHANGELOG.md) and
[code of conduct](https://github.com/smuniharish/agskillmanager/blob/master/CODE_OF_CONDUCT.md).

```console
uv sync --locked --all-extras --all-groups
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyrefly check
uv run --no-sync pytest --cov
uv run --no-sync zensical build --strict
uv run --no-sync python scripts/check_site_links.py
uv build
uvx twine check --strict dist/*
```

Full coverage requires `SKILL_MANAGER_TEST_POSTGRES_DSN` pointing at a disposable
PostgreSQL database. CI tests Python 3.12–3.15, lowest direct dependencies and a
core wheel without LangChain/LangGraph. Never weaken the coverage target to hide
untested paths.

## Publishing

1. Connect the repository to Read the Docs as `agskillmanager`; use `.readthedocs.yaml`.
2. Verify CI, docs and wheel checks.
3. Build and check the distributions with `uv build` and
   `uvx twine check --strict dist/*`, then upload them with `uv publish`.
4. Confirm the PyPI page, documentation and dynamic badges after publication.

No API tokens belong in the repository. Remote publication status is separate
from successful local builds.
