# Security

Skills are instructions, not trusted code. Validate and authorize them before
passing a bundle to an agent with tools. Enable human approval for untrusted
generation. The package does not authenticate reviewers.

- YAML is safely parsed, duplicate keys rejected and document size bounded.
- Filesystem sources refuse symbolic links and path escapes.
- SQL values are parameterized; identifiers are validated.
- Credential-like feedback metadata keys are rejected.
- Operational events exclude raw instructions and query text.
- Never store secrets in Skills, feedback, prompts or reviewer reasons.
- Use TLS, scoped credentials, backups and least-privilege storage roles.
- Enforce application access controls for catalogs and MCP servers.

Frozen Pydantic models do not recursively freeze arbitrary dictionaries; treat
nested mappings as read-only and use new validated revisions for content changes.

Report privately through [GitHub security advisories](https://github.com/smuniharish/skill-manager/security/advisories/new).
See [SECURITY.md](https://github.com/smuniharish/skill-manager/blob/master/SECURITY.md).
