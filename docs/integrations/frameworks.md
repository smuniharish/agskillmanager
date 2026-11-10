# Agent frameworks

Core never executes Skills or requires a framework. Build a bundle and pass it
to your runtime:

```python
bundle = await manager.build_bundle(["summarize-ticket"])
system_prompt = "\n".join(bundle.instructions)
```

- **Plain Python, Agno, CrewAI or custom runtimes:** use the prompt at the
  framework's instruction boundary; adapt capability data to its tool API.
- **LangGraph:** capture the bundle in an async node and call the model there.
- **LangChain:** pass `system_prompt=` and caller-owned tools to `create_agent`.
- **deepagents:** pass the same prompt to `create_deep_agent`.

Framework examples live in the `examples` dependency group. Install
`agskillmanager[langchain]` only for `XStructuredSkillGenerator` or `LangChainEmbedder`.
Applications choose and own model clients.

Generation wraps any runnable with xstructured, forwarding supplied options and
adding parent/rejection context when revising. Model/transport errors propagate;
invalid structured output raises `SkillGenerationError`.
See [Examples](../examples/index.md).
