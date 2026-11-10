---
name: skill-manager-extend
description: >-
  Use when extending skill-manager with a custom SkillSource, SkillRegistry,
  SkillGenerator, SkillValidator, DiscoveryProvider, retriever, reranker,
  embedding provider or observability sink. Also use to debug failing
  SkillSourceContract or SkillRegistryContract tests and adapt database or
  framework-specific integrations. For ordinary registration, approval,
  discovery or bundle usage use the skill-manager skill instead.
license: Apache-2.0
compatibility: Python 3.12+ with skill-manager 1.x. Templates and contract runner work offline.
metadata:
  version: "1.0.0"
  documentation: "https://skill-manager.readthedocs.io/en/latest/api/extensions/"
---

# Extend Skill Manager

Use existing async ABC seams. Never introduce a second lifecycle or storage facade.

## Workflow

1. Inspect the current public ABC and its async signatures. Choose the narrowest
   seam; do not patch private manager attributes.
2. For storage, copy [source_template.py](./assets/source_template.py) and replace
   dictionary operations with real backend operations. Preserve locator stability,
   idempotent replacement, source identity and delete behavior.
3. Run [check_source.py](./scripts/check_source.py) with `module:factory`. For
   registries, subclass `SkillRegistryContract` and implement `make_registry`
   returning an empty disposable backend.
4. For generation copy [generator_template.py](./assets/generator_template.py).
   Return a validated Skill, consume parent/rejection context and let the manager
   assign governance and lineage.
5. Preserve downstream configuration by accepting built clients, pools or runtimes.
   Document whether the adapter owns them; close only owned resources.
6. Add failure, cancellation, concurrency and real-backend tests. Translate
   backend-specific errors into package errors with chained causes; never turn
   failures into empty success results.
7. Run contracts, lint, type checks and one real integration call.

## Resources

- [Contracts and extension guidance](./references/contracts.md)
- [Source template](./assets/source_template.py)
- [Generator template](./assets/generator_template.py)
- [Contract runner](./scripts/check_source.py)
- [Evaluation tasks](./evals/evals.json)

Semantic embeddings use `mcp_capability_router.Embedder`; implement its two async
methods instead of adding another abstraction. All package extension points are ABCs.
