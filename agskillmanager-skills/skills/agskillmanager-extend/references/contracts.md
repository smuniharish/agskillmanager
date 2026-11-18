# Extension contracts

Sources return snapshots of locator-to-YAML mappings, save by immutable Skill ID,
replace idempotently and ignore unknown IDs on delete.

Registries must enforce immutable content, reject stale writes, permit idempotent
rewrites, maintain one active revision per name/version, and support lifecycle
replacement and state-filtered listing. Apply SkillRegistryContract to each backend.

Generators return Skill data and accept SkillGenerationRequest, including parent
and rejection history. Validators return a Skill or raise SkillValidationError.
Discovery providers return at most `top_k` active Skills that match the filters, never
invented or duplicated Skills, and release owned resources in `aclose`. RetrievalLoom
embedding models must return vectors of their declared `dimensions`; rerankers score
only the items they receive. Sinks receive sanitized events.

Use explicit ownership and backend-specific chained exceptions. Database adapters
must preserve atomicity and concurrent-write guarantees, not merely pass sequential tests.
