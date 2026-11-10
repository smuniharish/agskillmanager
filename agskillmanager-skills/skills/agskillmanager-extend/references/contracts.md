# Extension contracts

Sources return snapshots of locator-to-YAML mappings, save by immutable Skill ID,
replace idempotently and ignore unknown IDs on delete.

Registries must enforce immutable content, reject stale writes, permit idempotent
rewrites, maintain one active revision per name/version, and support lifecycle
replacement and state-filtered listing. Apply SkillRegistryContract to each backend.

Generators return Skill data and accept SkillGenerationRequest, including parent
and rejection history. Validators return a Skill or raise SkillValidationError.
Retrievers return bounded active filtered candidates; rerankers return only their
provided candidates without duplication. Sinks receive sanitized events.

Use explicit ownership and backend-specific chained exceptions. Database adapters
must preserve atomicity and concurrent-write guarantees, not merely pass sequential tests.
