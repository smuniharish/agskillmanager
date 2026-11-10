# Configuration

`SkillManagerConfig` controls agent creation, approval, document size, MCP
candidate/cache limits, feedback context and bounded error history.
Default approval is false; explicitly enable it for generated instructions.

Use a persistent source for approved YAML. Pending revisions live in the registry.
For restart-safe review, persist both registry and feedback-manager state.
Otherwise approvals cannot be verified after restarting and source agents return
to review.
