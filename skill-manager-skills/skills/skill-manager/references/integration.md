# Integrations

Core needs no agent framework. Feed `"\n".join(bundle.instructions)` to the
framework's instruction boundary. Resolve tools through the application's MCP runtime.

Install `[langchain]` for `XStructuredSkillGenerator` and `LangChainEmbedder`,
`[postgres]` for psycopg storage, `[otel]` for the OTel sink, or `[all]`.
Construct feedback-manager, MCPRuntime, RefreshEngine and XAIRuntime with all
required custom stores/policies/plugins, then inject them unchanged.
