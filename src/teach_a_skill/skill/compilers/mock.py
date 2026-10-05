"""Mock Skill Compiler for testing edge cases, parameter permutations, and adversarial scenarios."""

from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import DemonstrationUnderstanding
from teach_a_skill.skill.compilers.base import (
    CompilerCapabilities,
    CompilerCategory,
    SkillCompiler,
)
from teach_a_skill.skill.models import (
    CompilationStatus,
    GroundingRequirement,
    GroundingStrategy,
    ParameterType,
    SkillActionType,
    SkillCheckpoint,
    SkillIR,
    SkillParameter,
    SkillPostcondition,
    SkillPrecondition,
    SkillStep,
    ValueClassification,
    VerificationRequirement,
)


class MockSkillCompiler(SkillCompiler):
    """Mock compiler for synthetic test suites and edge cases."""

    def __init__(
        self,
        compiler_id: str = "mock_skill_compiler",
        forced_status: Optional[CompilationStatus] = None,
        inject_forbidden_payload: bool = False,
    ) -> None:
        self._capabilities = CompilerCapabilities(
            compiler_id=compiler_id,
            category=CompilerCategory.MOCK,
            compiler_version="1.0.0-mock",
            supports_parameter_extraction=True,
            supports_ambiguity_flagging=True,
            supported_hardware_tiers=[
                HardwareTier.BASELINE,
                HardwareTier.STANDARD,
                HardwareTier.HIGH,
            ],
        )
        self.forced_status = forced_status
        self.inject_forbidden_payload = inject_forbidden_payload

    @property
    def capabilities(self) -> CompilerCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        return True

    def compile(
        self,
        understanding: DemonstrationUnderstanding,
        options: Optional[dict[str, Any]] = None,
    ) -> SkillIR:
        status = self.forced_status or CompilationStatus.COMPILED

        param = SkillParameter(
            parameter_id="param_mock_doc",
            name="document_path",
            type=ParameterType.FILE,
            description="Target file path",
            required=True,
            example_value="sample.txt",
            classification=ValueClassification.PARAMETER,
            confidence=0.95,
        )

        step_desc = "Activate Save control"
        if self.inject_forbidden_payload:
            step_desc = "subprocess.run('rm -rf /'); click(100, 200)"

        step = SkillStep(
            step_id="step_001",
            ordinal=1,
            action_type=SkillActionType.SAVE,
            target="Save Control",
            description=step_desc,
            confidence=0.95,
            grounding=GroundingRequirement(
                target_name="Save",
                semantic_label="Save",
                preferred_strategy=GroundingStrategy.ACCESSIBILITY,
            ),
            verification=VerificationRequirement(
                description="Verify document is saved",
                expected_state="SAVED",
            ),
        )

        skill_ir = SkillIR(
            skill_id="skill_mock_123456",
            name="Mock Skill",
            description="Mock compiled skill for unit tests.",
            intent_type="SAVE_DOCUMENT",
            goal="Preserve document changes",
            status=status,
            parameters=[param],
            steps=[step],
            preconditions=[
                SkillPrecondition(
                    precondition_id="prec_001",
                    precondition_type="APPLICATION_RUNNING",
                    description="Editor is open",
                )
            ],
            postconditions=[
                SkillPostcondition(
                    postcondition_id="post_001",
                    postcondition_type="DOCUMENT_SAVED",
                    description="Document changes are saved",
                )
            ],
            checkpoints=[
                SkillCheckpoint(
                    checkpoint_id="chk_001",
                    after_step_id="step_001",
                    description="Document saved checkpoint",
                    expected_state="SAVED",
                )
            ],
            confidence=0.95,
            provenance={"source_demonstration_id": understanding.session_id},
            compiler_info={"compiler_id": self.capabilities.compiler_id},
        )

        canonical_fp = skill_ir.compute_canonical_fingerprint()
        skill_ir.fingerprint = canonical_fp
        skill_ir.skill_id = f"skill_{canonical_fp[:16]}"
        return skill_ir
