# Refresh and operations

`await manager.refresh()` reloads sources, rebuilds discovery and invalidates
capability caches. With a `RefreshEngine`, it first forwards `mode`,
`resource_ids`, `selector`, `trigger`, `metadata` and `correlation_id` to that engine.

Healthy sources are committed even if another fails. Failure raises
`SkillSourceError`; inspect `source_errors` for details. Do not treat a partially
healthy catalog as complete without checking errors.

`await manager.schedule_refresh(interval, run_immediately=False, events=None)`
starts an `AsyncScheduler`, stopped by `manager.aclose()`. A second scheduler
raises `SkillGovernanceError`. For external scheduling, schedule the public
`manager.refresh` coroutine yourself, retaining all scheduler-specific options.

Keyed locks serialize in-process writes. Shared PostgreSQL registries add database
enforcement across processes. Writes across source, registry and feedback systems
use compensation, not atomic cross-system transactions. Provision backups and
reconcile operational failures.

Logs use Python logging. Lifecycle events exclude raw instruction and query
contents. Sink or XAI failures are logged and retained in bounded
`observability_errors` without hiding the business result.
