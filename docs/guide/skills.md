# Skills and bundles

A `Skill` is frozen Pydantic data, not executable code. It contains:

- Generated `skill_id`, positive `revision` and name/version metadata.
- Instructions, prompts, resources, dependencies and required capabilities.
- Provenance: origin, source, creation time and parent IDs.
- Lifecycle: `ACTIVE`, `PENDING_APPROVAL` or `REJECTED`.
- Governance: feedback event IDs, reviewer and reason.

Use `dump_skill_yaml(skill)` and `await parse_skill_yaml(text)` for canonical
serialization and validated input. YAML parsing runs off the event loop, rejects
duplicate keys and enforces a document-size limit.

Register new content under a new ID. Idempotently writing the same revision is
allowed; changing instructions in place is not. Name/version lookup selects
an active revision; ID lookup can inspect pending and rejected revisions.

`build_bundle` resolves dependency-first order, combines instructions and
resources, checks prompt-key conflicts and resolves MCP requirements. It returns
validated application data; it neither runs an agent nor grants authorization.
