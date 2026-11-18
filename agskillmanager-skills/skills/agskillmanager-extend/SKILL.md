---
name: agskillmanager-extend
description: >-
  Use when extending agskillmanager with a custom SkillSource, SkillRegistry,
  SkillGenerator, SkillValidator, DiscoveryProvider, RetrievalLoom embedding
  model, reranker or NLI component, or observability sink. Also use to debug failing
  SkillSourceContract or SkillRegistryContract tests and adapt database or
  framework-specific integrations. For ordinary registration, approval,
  discovery or bundle usage use the agskillmanager skill instead.
license: Apache-2.0
compatibility: Python 3.12-3.14 with agskillmanager 2.x. Templates and contract runner work offline.
metadata:
  version: "2.0.0"
  documentation: "https://agskillmanager.readthedocs.io/en/latest/api/extensions/"
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

Discovery runs on `RetrievalLoomDiscoveryProvider`. For semantic search, reranking or
NLI implement RetrievalLoom's `EmbeddingModelABC`, `RerankerABC` or `NLIABC` and pass
them as `Components`; do not add another abstraction. All package extension points are ABCs.
