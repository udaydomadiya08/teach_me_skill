"""Recovery planner for Phase 11.

Generates bounded, policy-compliant RecoveryPlans from classified failures.
Enforces the finite recovery strategy set, strict risk evaluation,
and budget constraints.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from teach_a_skill.execution.models import ActionType, PlannedAction, SafetyLevel
from teach_a_skill.recovery.classifier import classify_action_idempotency
from teach_a_skill.recovery.models import (
    ActionIdempotency,
    FailureRecord,
    FailureSeverity,
    FailureType,
    Recoverability,
    RecoveryBudget,
    RecoveryPlan,
    RecoveryPolicy,
    RecoveryStrategy,
)
from teach_a_skill.skill.models import SkillStep

logger = logging.getLogger(__name__)


class RecoveryPlanner:
    """Plans recovery actions according to policy, budget, and failure classification."""

    def __init__(self, policy: Optional[RecoveryPolicy] = None) -> None:
        self.policy = policy or RecoveryPolicy()

    def plan_recovery(
        self,
        failure: FailureRecord,
        step: Optional[SkillStep],
        last_action: Optional[PlannedAction],
        budget: RecoveryBudget,
    ) -> RecoveryPlan:
        """Formulate a structured RecoveryPlan for a classified failure."""
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        step_id = step.step_id if step else (last_action.step_id if last_action else "unknown_step")

        # 1. Budget Exhaustion Check
        if not budget.can_attempt_step_recovery(step_id, action_cost=1, risk_cost=1):
            return RecoveryPlan(
                plan_id=plan_id,
                failure_id=failure.failure_id,
                recovery_strategy=RecoveryStrategy.STOP,
                candidate_actions=[],
                confidence=1.0,
                risk=SafetyLevel.SAFE,
                budget_cost=0,
                expected_state={},
                abort_conditions=["recovery_budget_exhausted"],
                explanation=f"Recovery budget exhausted for step '{step_id}' or execution",
            )

        # 2. Non-Recoverable Failures (Security, Critical Policy, etc.)
        if failure.recoverability == Recoverability.NON_RECOVERABLE:
            return RecoveryPlan(
                plan_id=plan_id,
                failure_id=failure.failure_id,
                recovery_strategy=RecoveryStrategy.STOP,
                candidate_actions=[],
                confidence=1.0,
                risk=SafetyLevel.CRITICAL if failure.severity == FailureSeverity.CRITICAL else SafetyLevel.HIGH,
                budget_cost=0,
                expected_state={},
                abort_conditions=["non_recoverable_failure"],
                explanation=f"Cannot recover from {failure.failure_type.value}: {failure.explanation}",
            )

        # 3. Supervised Recoverability / Manual Intervention
        if failure.recoverability == Recoverability.MANUAL_INTERVENTION_REQUIRED:
            return RecoveryPlan(
                plan_id=plan_id,
                failure_id=failure.failure_id,
                recovery_strategy=RecoveryStrategy.ESCALATE,
                candidate_actions=[],
                confidence=1.0,
                risk=SafetyLevel.MODERATE,
                budget_cost=0,
                expected_state={},
                abort_conditions=["manual_intervention_required"],
                explanation=f"Escalating for human intervention: {failure.explanation}",
            )

        # 4. Strategy Selection based on Canonical Failure Types

        # A. FOCUS_LOST -> REFOCUS
        if failure.failure_type == FailureType.FOCUS_LOST:
            app_name = step.parameters.get("expected_application") if step else None
            actions: list[PlannedAction] = []
            if app_name:
                actions.append(
                    PlannedAction(
                        action_id=f"rec_act_{uuid.uuid4().hex[:8]}",
                        step_id=step_id,
                        action_type=ActionType.ACTIVATE_APP,
                        target_x=0.0,
                        target_y=0.0,
                        parameters={"app_name": app_name},
                        safety_level=SafetyLevel.SAFE,
                    )
                )
            return RecoveryPlan(
                plan_id=plan_id,
                failure_id=failure.failure_id,
                recovery_strategy=RecoveryStrategy.REFOCUS,
                candidate_actions=actions,
                confidence=0.9,
                risk=SafetyLevel.SAFE,
                budget_cost=1,
                expected_state={"expected_application": app_name},
                abort_conditions=["application_not_available"],
                explanation=f"Attempting to refocus application '{app_name}'",
            )

        # B. TEMPORARY_LOADING / TEMPORARY_DISABLED_STATE -> WAIT_FOR_STATE
        if failure.failure_type in (
            FailureType.TEMPORARY_LOADING,
            FailureType.TEMPORARY_DISABLED_STATE,
        ):
            wait_action = PlannedAction(
                action_id=f"rec_act_{uuid.uuid4().hex[:8]}",
                step_id=step_id,
                action_type=ActionType.WAIT,
                target_x=0.0,
                target_y=0.0,
                parameters={"seconds": 1.0},
                safety_level=SafetyLevel.SAFE,
            )
            return RecoveryPlan(
                plan_id=plan_id,
                failure_id=failure.failure_id,
                recovery_strategy=RecoveryStrategy.WAIT_FOR_STATE,
                candidate_actions=[wait_action],
                confidence=0.85,
                risk=SafetyLevel.SAFE,
                budget_cost=1,
                expected_state={"loading_cleared": True},
                abort_conditions=["wait_timeout_exceeded"],
                explanation="Waiting bounded duration for transient loading to clear",
            )

        # C. TARGET_MOVED, TARGET_RENAMED, GROUNDING_FAILURE, TRANSIENT_UI_CHANGE -> REGROUND
        if failure.failure_type in (
            FailureType.TARGET_MOVED,
            FailureType.TARGET_RENAMED,
            FailureType.GROUNDING_FAILURE,
            FailureType.TRANSIENT_UI_CHANGE,
            FailureType.AMBIGUOUS_TARGET,
        ):
            if not self.policy.allow_regrounding:
                return RecoveryPlan(
                    plan_id=plan_id,
                    failure_id=failure.failure_id,
                    recovery_strategy=RecoveryStrategy.STOP,
                    candidate_actions=[],
                    confidence=1.0,
                    risk=SafetyLevel.SAFE,
                    budget_cost=0,
                    abort_conditions=["regrounding_prohibited_by_policy"],
                    explanation="Recovery policy disallows re-grounding",
                )

            return RecoveryPlan(
                plan_id=plan_id,
                failure_id=failure.failure_id,
                recovery_strategy=RecoveryStrategy.REGROUND,
                candidate_actions=[],  # Re-grounder will supply fresh actions
                confidence=0.8,
                risk=SafetyLevel.SAFE,
                budget_cost=1,
                expected_state={"target_grounded": True},
                abort_conditions=["regrounding_failed"],
                explanation=f"Re-observing live environment to re-ground target for {failure.failure_type.value}",
            )

        # D. TIMEOUT
        if failure.failure_type == FailureType.TIMEOUT:
            action_type = last_action.action_type if last_action else ActionType.NOOP
            idempotency = classify_action_idempotency(action_type)

            if idempotency == ActionIdempotency.IDEMPOTENT and last_action:
                return RecoveryPlan(
                    plan_id=plan_id,
                    failure_id=failure.failure_id,
                    recovery_strategy=RecoveryStrategy.RETRY_IDEMPOTENT,
                    candidate_actions=[last_action],
                    confidence=0.75,
                    risk=SafetyLevel.SAFE,
                    budget_cost=1,
                    expected_state={},
                    abort_conditions=["retry_timeout"],
                    explanation="Retrying idempotent action after timeout",
                )
            else:
                # Non-idempotent or unknown: never blindly retry!
                return RecoveryPlan(
                    plan_id=plan_id,
                    failure_id=failure.failure_id,
                    recovery_strategy=RecoveryStrategy.REOBSERVE,
                    candidate_actions=[],
                    confidence=0.7,
                    risk=SafetyLevel.MODERATE,
                    budget_cost=1,
                    expected_state={},
                    abort_conditions=["uncertain_completion_state"],
                    explanation=(
                        f"Non-idempotent action '{action_type.value}' timed out; "
                        f"must re-observe environment before deciding next step"
                    ),
                )

        # E. POSTCONDITION_FAILURE / ACTION_FAILURE
        if failure.failure_type in (
            FailureType.POSTCONDITION_FAILURE,
            FailureType.ACTION_FAILURE,
        ):
            # Check if action was idempotent
            action_type = last_action.action_type if last_action else ActionType.NOOP
            idempotency = classify_action_idempotency(action_type)

            if idempotency == ActionIdempotency.IDEMPOTENT and last_action:
                return RecoveryPlan(
                    plan_id=plan_id,
                    failure_id=failure.failure_id,
                    recovery_strategy=RecoveryStrategy.RETRY_IDEMPOTENT,
                    candidate_actions=[last_action],
                    confidence=0.75,
                    risk=SafetyLevel.SAFE,
                    budget_cost=1,
                    expected_state={},
                    abort_conditions=["retry_exhausted"],
                    explanation=f"Retrying idempotent action {action_type.value} after postcondition check failed",
                )
            else:
                return RecoveryPlan(
                    plan_id=plan_id,
                    failure_id=failure.failure_id,
                    recovery_strategy=RecoveryStrategy.REOBSERVE,
                    candidate_actions=[],
                    confidence=0.7,
                    risk=SafetyLevel.MODERATE,
                    budget_cost=1,
                    expected_state={},
                    abort_conditions=[],
                    explanation="Re-observing environment after verification failure",
                )

        # Default fallback
        return RecoveryPlan(
            plan_id=plan_id,
            failure_id=failure.failure_id,
            recovery_strategy=RecoveryStrategy.STOP,
            candidate_actions=[],
            confidence=0.5,
            risk=SafetyLevel.SAFE,
            budget_cost=0,
            expected_state={},
            abort_conditions=["unknown_failure_type"],
            explanation=f"No automatic recovery available for failure type {failure.failure_type.value}",
        )
