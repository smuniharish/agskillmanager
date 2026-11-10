# Installation

Python 3.12 through 3.15 are tested.

```console
pip install skill-manager
pip install "skill-manager[langchain]"
pip install "skill-manager[postgres,otel]"
pip install "skill-manager[all]"
```

| Extra | Included |
|---|---|
| `langchain` | LangChain Core, xstructured generation, LangChain embedding adapter |
| `postgres` | psycopg binary driver and async pool |
| `otel` | OpenTelemetry API and SDK |
| `all` | Every extra above |

Model providers, agent frameworks and telemetry exporters are application choices.
The repository's `examples` group installs the libraries used by its examples.

```console
git clone https://github.com/smuniharish/skill-manager.git
cd skill-manager
uv sync --locked --all-extras --all-groups
uv run --no-sync python examples/quickstart.py
```
