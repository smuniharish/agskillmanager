# Architecture

```text
SkillSource -- YAML --> parser / SkillValidator --> SkillRegistry
                                                    |
                                  DiscoveryProvider / dependency resolver
                                                    |
                    SkillBundle <--- MCPRuntime capability resolution
                         |
                    your agent runtime
```

The manager coordinates lifecycle policy. Generators supply candidates;
feedback-manager records reviews; refresh-engine updates external resources;
agxai and OTel receive decisions and events.

Core imports no optional framework. Optional implementations live in explicit
modules. Models are frozen, extra-forbid Pydantic data. I/O and extension methods
are async; filesystem/YAML work runs in threads where needed.

Keyed locks serialize writes without accumulating unused locks. Capability caches
and error histories are bounded. Source failures are isolated. PostgreSQL adds
cross-process active-revision uniqueness.

Application-created collaborators are application-owned. Separate services use
compensation rather than one transaction. Restart-safe review needs durable
registry and feedback storage.
