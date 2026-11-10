# Architecture

Sources return locator-to-YAML mappings. The manager parses and validates them
into a registry, indexes discovery, governs lifecycle and returns bundles.
Frameworks execute the instructions. Sources, registries and framework clients
remain independent.

Injected resources remain caller-owned. The manager closes its own default
feedback manager and scheduler only. Keep a single manager for a catalog's
in-process writes. Use PostgreSQL registry enforcement across processes.
