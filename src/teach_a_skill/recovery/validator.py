"""Safety and boundary validator for Phase 11 recovery.

Formally tests and validates recovery invariants:
1. No recovery action can bypass base execution safety policy.
2. Recovery cannot escalate execution authority.
3. Recovery cannot modify SkillIR or publish new skill versions (immutability).
4. Recovery cannot execute arbitrary code, shell commands, or osascript injections.
5. Recovery terminates deterministically within bounded budgets.
"""

from __future__ import annotations

import logging
from typing import Any

from teach_a_skill.execution.models import (
    ActionType,
    ExecutionPolicy,
    PlannedAction,
    SafetyLevel,
)
from teach_a_skill.execution.safety import SafetyEnforcer
from teach_a_skill.recovery.models import (
    FailureRecord,
    FailureType,
    RecoveryBudget,
    RecoveryPlan,
    RecoveryPolicy,
    RecoveryStrategy,
)
from teach_a_skill.skill.models import SkillIR

logger = logging.getLogger(__name__)


class RecoveryValidator:
    """Validates Phase 11 recovery safety invariants and structural boundaries."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        recovery_policy: Optional[RecoveryPolicy] = None,
    ) -> None:
        self.exec_policy = execution_policy or ExecutionPolicy.DRY_RUN
        self.rec_policy = recovery_policy or RecoveryPolicy()
        self.safety = SafetyEnforcer()

    def validate_action_safety(self, action: PlannedAction) -> tuple[bool, str]:
        """Invariant 1 & 4: Recovery actions must pass normal execution safety policy

        and cannot execute shell/code/arbitrary commands.
        """
        # Block arbitrary commands or shell tokens in parameters
        params_str = str(action.parameters).lower()
        forbidden_tokens = ["rm -rf", "sudo", "eval(", "exec(", "sh -c", "bash -c", "osascript -e", ";", "&&", "|"]
        for token in forbidden_tokens:
            if token in params_str and action.action_type not in (ActionType.NOOP, ActionType.WAIT):
                return False, f"Dangerous command injection token '{token}' detected in action parameters"

        # Check against Phase 10 execution safety policy
        eval_res = self.safety.assess_action(action, self.exec_policy)
        if not eval_res.safe:
            return False, f"Recovery action rejected by execution safety policy: {eval_res.blocked_reason}"

        return True, "Action conforms to safety and boundary policies"

    def validate_authority_boundary(
        self,
        base_policy: ExecutionPolicy,
        recovery_plan: RecoveryPlan,
    ) -> tuple[bool, str]:
        """Invariant 2: Recovery cannot increase execution authority or risk limits."""
        for act in recovery_plan.candidate_actions:
            if act.safety_level == SafetyLevel.BLOCKED:
                return False, f"Recovery plan contains action type '{act.action_type.value}' blocked by policy"
            if act.safety_level in (SafetyLevel.HIGH_RISK, SafetyLevel.BLOCKED) and base_policy == ExecutionPolicy.DRY_RUN:
                return False, "High-risk recovery action attempted under dry run policy"
        return True, "Recovery plan conforms to authority boundaries"

    def validate_skill_immutability(
        self,
        skill_before: SkillIR,
        skill_after: SkillIR,
    ) -> tuple[bool, str]:
        """Invariant 3: SkillIR, steps, and parameters must remain strictly immutable

        across execution and recovery.
        """
        if skill_before.skill_id != skill_after.skill_id:
            return False, "Skill ID mutated"
        if skill_before.version != skill_after.version:
            return False, "Skill version was modified during recovery (silent versioning violation)"
        if len(skill_before.steps) != len(skill_after.steps):
            return False, "Skill step count mutated"

        for s1, s2 in zip(skill_before.steps, skill_after.steps):
            if s1.to_dict() != s2.to_dict():
                return False, f"Skill step '{s1.step_id}' mutated during execution or recovery"

        return True, "Skill immutability strictly preserved"

    def validate_bounded_termination(
        self,
        budget: RecoveryBudget,
        step_id: str,
    ) -> tuple[bool, str]:
        """Invariant 5: Recovery loop must terminate when budget is exhausted."""
        can_attempt = budget.can_attempt_step_recovery(step_id)
        if (
            budget.total_retries_used >= budget.execution_retry_budget
            or budget.step_retries_used.get(step_id, 0) >= budget.step_retry_budget
            or budget.elapsed_time_s >= budget.time_budget_s
        ):
            if can_attempt:
                return False, "Budget exhaustion was not properly enforced (infinite loop potential)"
        return True, "Recovery termination budget verified"

    def run_all_validation_checks(self) -> dict[str, Any]:
        """Run comprehensive validation suite covering all Phase 11 safety invariants."""
        # 1. Action Safety Test
        safe_action = PlannedAction(
            action_id="val_1",
            step_id="step_1",
            action_type=ActionType.CLICK,
            target_x=10.0,
            target_y=10.0,
            grounding_confidence=0.9,
            safety_level=SafetyLevel.SAFE,
        )
        safe_ok, safe_msg = self.validate_action_safety(safe_action)

        # 2. Command Injection Test
        bad_action = PlannedAction(
            action_id="val_2",
            step_id="step_1",
            action_type=ActionType.TYPE_TEXT,
            target_x=10.0,
            target_y=10.0,
            parameters={"text": "rm -rf /; sudo reboot"},
            safety_level=SafetyLevel.SAFE,
        )
        bad_ok, bad_msg = self.validate_action_safety(bad_action)

        # 3. Immutability Test
        from teach_a_skill.skill.models import SkillActionType, SkillStep
        step = SkillStep(
            step_id="s1",
            ordinal=0,
            action_type=SkillActionType.SELECT,
            target="button",
            description="click",
        )
        sk1 = SkillIR(
            skill_id="sk1",
            name="Test",
            description="test skill",
            intent_type="click",
            goal="test goal",
            schema_version="1.0.0",
            steps=[step],
        )
        sk2 = SkillIR(
            skill_id="sk1",
            name="Test",
            description="test skill",
            intent_type="click",
            goal="test goal",
            schema_version="1.0.0",
            steps=[step],
        )
        mut_ok, mut_msg = self.validate_skill_immutability(sk1, sk2)

        # 4. Budget Test
        b = RecoveryBudget(step_retry_budget=2, execution_retry_budget=5)
        b.consume("s1", 1.0)
        b.consume("s1", 1.0)
        bud_ok, bud_msg = self.validate_bounded_termination(b, "s1")

        all_passed = safe_ok and (not bad_ok) and mut_ok and bud_ok
        return {
            "all_passed": all_passed,
            "action_safety": {"passed": safe_ok, "detail": safe_msg},
            "injection_defense": {"passed": not bad_ok, "detail": bad_msg},
            "skill_immutability": {"passed": mut_ok, "detail": mut_msg},
            "bounded_budget": {"passed": bud_ok, "detail": bud_msg},
        }
