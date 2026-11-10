# Governance and feedback

Enable `require_human_approval=True` wherever model-generated instructions require
review. Implement the async `SkillGenerator` ABC, or install the `langchain` extra
and construct `XStructuredSkillGenerator(model, repair=..., **options)`.

```python
from skill_manager import SkillManager, SkillManagerConfig


async def review(generator):
    async with SkillManager(config=SkillManagerConfig(require_human_approval=True)) as manager:
        candidate = await manager.generate_skill(generator, "Summarize safely")
        await manager.reject_skill(candidate.skill_id, feedback="Add privacy instructions.")
        revised = await manager.generate_skill(
            generator, "Apply the review", parent_skill_id=candidate.skill_id
        )
        return await manager.approve_skill(revised.skill_id, reviewer="reviewer:ana")
```

Pending revisions stay in the registry, not the Skill source, until approved.
Rejected revisions remain inspectable and cannot be removed through `remove_skill`.
Regeneration receives the parent and rejections, increments revision and records lineage.

Review uses feedback-manager: submit and handle feedback, persist the lifecycle,
then close feedback. Failure to close restores the previous lifecycle. Persistence
failures raise explicit errors. These are compensating writes, not a distributed transaction.

For restart-safe review, inject both a durable `SkillRegistry` and a durable
feedback store. An active agent Skill loaded from a source is held for review
unless its approval event is resolved in that feedback manager.

Reviewer metadata is not authentication. Enforce authorization before calling
approval APIs. Credential-like metadata keys are rejected recursively; never put
secrets in feedback text or instructions.
