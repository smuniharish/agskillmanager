# Contributing

Use Python 3.12 or newer and uv:

```console
uv sync --locked --all-extras --all-groups
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyrefly check
uv run --no-sync pytest
uv run --no-sync zensical build --strict
uv run --no-sync python scripts/check_site_links.py
```

Keep core framework-agnostic. Use async ABCs, explicit ownership, specific errors
and tested compensation for external writes. Add targeted tests and update related
examples/documentation. Public Python APIs use Google-style docstrings and type annotations.

For full coverage, start a disposable PostgreSQL 18 instance and set
`SKILL_MANAGER_TEST_POSTGRES_DSN`; see [service examples](docs/examples/index.md).
CI requires 100% line and branch coverage. Tests use warnings as errors.
Live LLM tests need an environment key and are skipped otherwise.

Validate portable skills with `agentskills validate` (from skills-ref) and the tests under
`tests/skill`. Never commit credentials, runtime catalogs or generated site files.
Open a pull request describing the problem, implementation and validation.
