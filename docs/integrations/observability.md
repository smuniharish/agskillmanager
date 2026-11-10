# OpenTelemetry and agxai

OTel records operational lifecycle signals. agxai records evidence-backed
generation, review and bundle decisions.

## OpenTelemetry

Install `skill-manager[otel]`. Inject `OpenTelemetrySkillObservabilitySink` with
explicit tracer/meter objects or providers. Otherwise global providers are used.
Every event produces a zero-duration span and increments `skill_manager.events`
with `event.name`.

Providers carry your sampling, resources, processors, readers and exporters.
`sink.aclose()` flushes injected providers; `owns_providers=True` shuts them down.
The manager never closes an injected sink.

The [OTel example](../examples/index.md#service-backed-examples) exports to Grafana
LGTM. Query Tempo for `service.name=skill-manager-example` and Prometheus for
`skill_manager_events_total`.

## agxai

Pass `xai_runtime=XAIRuntime(...)`. Decisions join an active run bound through
runtime context APIs; otherwise each operation gets a dedicated run.
Use `with runtime.collect_runs() as runs:` around operations, then
`await runtime.explain_decision(decision, run=run)`.

Configure storage, disclosure and instrumentation in agxai. Skill Manager records
identifiers and review metadata, not full instruction contents. Treat
reviewer-supplied text as potentially sensitive.

Telemetry failures are logged and retained in `observability_errors`; successful
business operations remain successful.
