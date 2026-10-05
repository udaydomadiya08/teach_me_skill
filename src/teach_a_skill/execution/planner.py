"""Execution planner: assembles grounding + actions + safety into a validated plan.

The planner takes a Skill IR, grounds all steps against the live environment,
translates them into platform actions, assesses safety, and produces a
complete ExecutionPlan ready for dry-run or real execution.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from teach_a_skill.execution.actions import ActionTranslator
from teach_a_skill.execution.environment import EnvironmentAdapter
from teach_a_skill.execution.grounding import SemanticGroundingEngine
from teach_a_skill.execution.models import (
    ExecutionPlan,
    ExecutionPolicy,
    GroundingResult,
    PlannedAction,
    SafetyLevel,
)
from teach_a_skill.execution.safety import ExecutionSafetyPolicy
from teach_a_skill.skill.models import SkillIR

logger = logging.getLogger(__name__)


class ExecutionPlanner:
    """Produces a validated ExecutionPlan from a Skill IR + live environment.

    Pipeline:
    1. Observe environment (snapshot)
    2. Ground all step targets
    3. Translate grounded steps to platform actions
    4. Assess safety of the plan
    5. Check preconditions
    6. Package as ExecutionPlan
    """

    def __init__(
        self,
        environment: EnvironmentAdapter,
        grounding_engine: Optional[SemanticGroundingEngine] = None,
        action_translator: Optional[ActionTranslator] = None,
        safety_policy: Optional[ExecutionSafetyPolicy] = None,
        platform: str = "macos",
    ) -> None:
        self.environment = environment
        self.grounding_engine = grounding_engine or SemanticGroundingEngine()
        self.action_translator = action_translator or ActionTranslator(platform=platform)
        self.safety_policy = safety_policy or ExecutionSafetyPolicy()

    def create_plan(
        self,
        skill_ir: SkillIR,
        policy: ExecutionPolicy = ExecutionPolicy.DRY_RUN,
        parameters: Optional[dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """Create a complete execution plan for a skill.

        Args:
            skill_ir: The compiled Skill IR to plan execution for.
            policy: Execution policy (DRY_RUN, SUPERVISED, AUTONOMOUS).
            parameters: Resolved parameter values for parameterized steps.

        Returns:
            An ExecutionPlan with grounding, actions, and safety assessment.
        """
        start = time.monotonic()

        # 1. Observe environment
        snapshot = self.environment.observe()

        # 2. Ground all steps
        grounding_results = self.grounding_engine.ground_all_steps(
            steps=skill_ir.steps,
            snapshot=snapshot,
            grounding_reqs=skill_ir.grounding_requirements,
        )

        # 3. Translate to platform actions
        planned_actions = self.action_translator.translate_all(
            steps=skill_ir.steps,
            groundings=grounding_results,
            parameters=parameters,
        )

        # 4. Safety assessment
        safety_report = self.safety_policy.assess_plan(planned_actions, policy)

        # 5. Check preconditions
        precondition_descs = [pc.description for pc in skill_ir.preconditions]
        env_state = {
            "active_app": snapshot.active_application or "",
            "active_window": snapshot.active_window_title or "",
            "running_apps": " ".join(snapshot.running_applications),
        }
        preconditions_met, unmet = self.safety_policy.enforce_preconditions(
            precondition_descs, env_state
        )

        # 6. Assess overall grounding
        all_grounded = all(g.grounded for g in grounding_results)
        confidences = [g.confidence for g in grounding_results if g.grounded]
        min_confidence = min(confidences) if confidences else 0.0

        # 7. Determine readiness
        ready = all_grounded and safety_report.safe and preconditions_met

        elapsed = (time.monotonic() - start) * 1000

        explanation_parts: list[str] = []
        if not all_grounded:
            ungrounded = [g.target_name for g in grounding_results if not g.grounded]
            explanation_parts.append(f"Ungrounded targets: {ungrounded}")
        if not safety_report.safe:
            explanation_parts.append(f"Safety blocked: {safety_report.blocked_reason}")
        if not preconditions_met:
            explanation_parts.append(f"Unmet preconditions: {unmet}")
        if ready:
            explanation_parts.append(
                f"Plan ready ({len(planned_actions)} actions, "
                f"min confidence {min_confidence:.2f}, "
                f"safety: {safety_report.safety_level})"
            )

        return ExecutionPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:12]}",
            skill_id=skill_ir.skill_id,
            skill_version=skill_ir.schema_version,
            policy=policy,
            planned_actions=planned_actions,
            grounding_results=grounding_results,
            all_grounded=all_grounded,
            minimum_confidence=min_confidence,
            overall_safety=safety_report.safety_level,
            preconditions_met=preconditions_met,
            ready_to_execute=ready,
            explanation=" | ".join(explanation_parts),
        )


ActionPlanner = ExecutionPlanner

