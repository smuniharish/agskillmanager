"""A generation seam independent of agent frameworks."""

from skill_manager import Skill, SkillGenerationRequest, SkillGenerator, SkillMetadata


class SupportSkillGenerator(SkillGenerator):
    async def generate(self, request: SkillGenerationRequest) -> Skill:
        instructions = ["Use verified facts.", "Remove personal information."]
        if request.feedback:
            instructions.append("Apply the reviewer-requested safety checks.")
        return Skill(
            metadata=SkillMetadata(
                name="support-review", version="1.0.0", description="Review support tickets."
            ),
            instructions=tuple(instructions),
        )
