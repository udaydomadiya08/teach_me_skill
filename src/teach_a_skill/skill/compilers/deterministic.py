"""Deterministic skill compiler translating Phase 7 semantic task understanding into Skill IR."""

import re
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import (
    ActionType,
    DemonstrationUnderstanding,
    IntentType,
)
from teach_a_skill.skill.compilers.base import (
    CompilerCapabilities,
    CompilerCategory,
    SkillCompiler,
)
from teach_a_skill.skill.models import (
    CompilationStatus,
    FailureConditionType,
    GroundingRequirement,
    GroundingStrategy,
    ParameterType,
    SkillActionType,
    SkillCheckpoint,
    SkillDependency,
    SkillFailureCondition,
    SkillIR,
    SkillParameter,
    SkillPostcondition,
    SkillPrecondition,
    SkillStep,
    SkillVariable,
    ValueClassification,
    VerificationRequirement,
)

logger = get_logger("teach_a_skill.skill.compilers.deterministic")


class DeterministicSkillCompiler(SkillCompiler):
    """Deterministic, inspectable rule-based compiler producing validated Skill IR.
    
    Guaranteed 100% offline, reproducible, and strictly non-executing.
    """

    def __init__(self) -> None:
        self._capabilities = CompilerCapabilities(
            compiler_id="deterministic_skill_compiler",
            category=CompilerCategory.DETERMINISTIC,
            compiler_version="1.0.0",
            supports_parameter_extraction=True,
            supports_ambiguity_flagging=True,
            supported_hardware_tiers=[
                HardwareTier.BASELINE,
                HardwareTier.STANDARD,
                HardwareTier.HIGH,
            ],
        )

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
        """Compile demonstration understanding into a structured Skill IR."""
        options = options or {}

        # 1. Determine Skill Name and Goal
        raw_name = understanding.task_name
        if understanding.primary_intent:
            intent_val = str(understanding.primary_intent.intent_type).replace("_", " ").title()
            skill_name = f"Skill: {intent_val}"
        else:
            skill_name = raw_name or "Demonstrated Skill"

        goal = understanding.goal or "Execute demonstrated semantic task."
        description = understanding.description or f"Portable compiled skill for {skill_name}."

        # 2. Determine Compilation Status and Handle Ambiguities
        status = CompilationStatus.COMPILED
        ambiguities_list = []
        if understanding.ambiguities:
            status = CompilationStatus.NEEDS_DISAMBIGUATION
            ambiguities_list = [a.to_dict() for a in understanding.ambiguities]
        elif understanding.confidence < 0.60:
            status = CompilationStatus.COMPILED_WITH_WARNINGS

        # 3. Parameter Extraction & Classification (Constants vs Parameters vs Dependencies)
        parameters: list[SkillParameter] = []
        dependencies: list[SkillDependency] = []
        param_names: set[str] = set()
        dep_names: set[str] = set()

        for ent in understanding.entities:
            # Application -> Environmental Dependency
            if ent.entity_type == "application":
                if ent.label not in dep_names:
                    dep_names.add(ent.label)
                    dep_id = f"dep_app_{ent.label.lower().replace(' ', '_')}"
                    dependencies.append(
                        SkillDependency(
                            dependency_id=dep_id,
                            dependency_type="application",
                            name=ent.label,
                            required=True,
                            description=f"Requires application '{ent.label}' installed and accessible.",
                            evidence_refs=[r.get("evidence_id", "") for r in ent.evidence_refs if isinstance(r, dict)],
                        )
                    )
            # File / Document -> Parameter Candidate
            elif ent.entity_type in ("document", "file"):
                p_name = f"{ent.label.lower().replace('.', '_').replace(' ', '_')}_path"
                if p_name not in param_names:
                    param_names.add(p_name)
                    parameters.append(
                        SkillParameter(
                            parameter_id=f"param_{p_name}",
                            name=p_name,
                            type=ParameterType.FILE,
                            description=f"File path for {ent.label}",
                            required=True,
                            example_value=ent.label,
                            classification=ValueClassification.PARAMETER,
                            source_evidence=ent.evidence_refs,
                            confidence=0.90,
                        )
                    )

        # Scan Semantic Actions for Input Text Parameters
        input_count = 1
        for act in understanding.actions:
            if act.action_type == ActionType.INPUT_TEXT:
                match = re.search(r"['\"](.*?)['\"]", act.description)
                example_val = match.group(1) if match else "Sample Input"
                p_name = f"user_text_{input_count}"
                if p_name not in param_names:
                    param_names.add(p_name)
                    parameters.append(
                        SkillParameter(
                            parameter_id=f"param_{p_name}",
                            name=p_name,
                            type=ParameterType.TEXT,
                            description=f"Input text entered during demonstration: '{example_val}'",
                            required=True,
                            example_value=example_val,
                            classification=ValueClassification.PARAMETER,
                            source_evidence=[{"action_id": act.action_id}],
                            confidence=act.confidence,
                        )
                    )
                    input_count += 1

        # 4. Compile Semantic Actions into Skill Steps
        steps: list[SkillStep] = []
        grounding_reqs: list[GroundingRequirement] = []

        action_type_mapping = {
            ActionType.ACTIVATE_CONTROL: SkillActionType.ACTIVATE,
            ActionType.INPUT_TEXT: SkillActionType.INPUT,
            ActionType.SWITCH_APPLICATION: SkillActionType.NAVIGATE,
            ActionType.FOCUS_WINDOW: SkillActionType.NAVIGATE,
            ActionType.NAVIGATE_VIEW: SkillActionType.NAVIGATE,
            ActionType.SELECT_OPTION: SkillActionType.SELECT,
            ActionType.HOTKEY_ACTION: SkillActionType.ACTIVATE,
            ActionType.INSPECT_REGION: SkillActionType.VERIFY_STATE,
        }

        for idx, act in enumerate(understanding.actions, 1):
            skill_action_type = action_type_mapping.get(act.action_type, SkillActionType.ACTIVATE)

            # Determine target entity or label
            target = "UI Target"
            if act.target_entities:
                target = act.target_entities[0]
            else:
                # Extract target from description
                match = re.search(r"Application '([^']+)'", act.description)
                if match:
                    target = match.group(1)
                else:
                    match_ctrl = re.search(r"near '([^']+)'", act.description)
                    if match_ctrl:
                        target = match_ctrl.group(1)

            # Build Grounding Requirement
            grd = GroundingRequirement(
                target_name=target,
                semantic_label=target,
                element_type="UI_CONTROL" if skill_action_type != SkillActionType.NAVIGATE else "WINDOW",
                application=target if skill_action_type == SkillActionType.NAVIGATE else None,
                preferred_strategy=GroundingStrategy.ACCESSIBILITY,
                fallback_strategies=[GroundingStrategy.OCR_TEXT, GroundingStrategy.UI_ROLE],
                evidence_refs=act.evidence_refs,
                confidence=act.confidence,
            )
            grounding_reqs.append(grd)

            # Build Verification Requirement
            verif = VerificationRequirement(
                description=f"Confirm {skill_action_type} on '{target}' completed successfully.",
                expected_state="STATE_COMPLETED",
                evidence_required=act.evidence_refs,
            )

            step = SkillStep(
                step_id=f"step_{idx:03d}",
                ordinal=idx,
                action_type=skill_action_type,
                target=target,
                description=act.description,
                arguments={},
                inputs=[],
                outputs=[],
                preconditions=[],
                postconditions=act.state_effects,
                grounding=grd,
                verification=verif,
                evidence_refs=act.evidence_refs,
                confidence=act.confidence,
                optional=False,
                source_semantic_action_id=act.action_id,
            )
            steps.append(step)

        # 5. Compile Preconditions & Postconditions
        preconditions: list[SkillPrecondition] = []
        for idx, p in enumerate(understanding.preconditions, 1):
            preconditions.append(
                SkillPrecondition(
                    precondition_id=f"prec_{idx:03d}",
                    precondition_type="ENVIRONMENT_STATE",
                    description=p.description,
                    observed=p.observed,
                    evidence_refs=p.evidence_refs,
                    confidence=1.0,
                )
            )

        postconditions: list[SkillPostcondition] = []
        for idx, po in enumerate(understanding.postconditions, 1):
            postconditions.append(
                SkillPostcondition(
                    postcondition_id=f"post_{idx:03d}",
                    postcondition_type="TASK_MILESTONE",
                    description=po.description,
                    observed=po.observed,
                    evidence_refs=po.evidence_refs,
                    confidence=1.0,
                )
            )

        # 6. Compile Checkpoints from State Transitions
        checkpoints: list[SkillCheckpoint] = []
        for idx, trans in enumerate(understanding.state_transitions, 1):
            matching_step = steps[-1].step_id if steps else "step_001"
            checkpoints.append(
                SkillCheckpoint(
                    checkpoint_id=f"chk_{idx:03d}",
                    after_step_id=matching_step,
                    description=trans.description,
                    expected_state=trans.after_state,
                    evidence_requirement=trans.evidence_refs,
                    confidence=1.0,
                )
            )

        # 7. Add Standard Semantic Variables
        variables = [
            SkillVariable(
                variable_id="var_active_app",
                name="current_active_application",
                type="string",
                source="runtime_window_tracker",
                lifetime="skill_execution",
            )
        ]

        # 8. Standard Failure Conditions
        failure_conditions = [
            SkillFailureCondition(
                condition_id="fail_target_missing",
                condition_type=FailureConditionType.TARGET_NOT_FOUND,
                description="Required UI target could not be resolved across accessibility and OCR fallbacks.",
            ),
            SkillFailureCondition(
                condition_id="fail_app_unavailable",
                condition_type=FailureConditionType.APPLICATION_UNAVAILABLE,
                description="Required application is not running or accessible.",
            ),
            SkillFailureCondition(
                condition_id="fail_timeout",
                condition_type=FailureConditionType.EXPECTED_STATE_NOT_REACHED,
                description="Step verification did not detect expected resulting state within timeout.",
            ),
        ]

        # 9. Assembly & Fingerprinting
        temp_ir = SkillIR(
            skill_id="temp_skill_id",
            name=skill_name,
            description=description,
            intent_type=str(understanding.primary_intent.intent_type) if understanding.primary_intent else "CUSTOM_INTERACTION",
            goal=goal,
            schema_version="1.0.0",
            status=status,
            parameters=parameters,
            variables=variables,
            dependencies=dependencies,
            preconditions=preconditions,
            steps=steps,
            checkpoints=checkpoints,
            postconditions=postconditions,
            failure_conditions=failure_conditions,
            grounding_requirements=grounding_reqs,
            evidence_refs=understanding.evidence_refs,
            confidence=understanding.confidence,
            ambiguities=ambiguities_list,
            provenance={
                "source_demonstration_id": understanding.session_id,
                "source_task_id": understanding.task_id,
                "compiler_id": self.capabilities.compiler_id,
                "compiler_version": self.capabilities.compiler_version,
            },
            compiler_info={
                "compiler_id": self.capabilities.compiler_id,
                "category": str(self.capabilities.category),
                "compiler_version": self.capabilities.compiler_version,
            },
        )

        canonical_fp = temp_ir.compute_canonical_fingerprint()
        deterministic_skill_id = f"skill_{canonical_fp[:16]}"

        temp_ir.skill_id = deterministic_skill_id
        temp_ir.fingerprint = canonical_fp

        return temp_ir
