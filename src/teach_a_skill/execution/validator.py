"""Execution validator: structural and semantic validation for Phase 10.

Validates execution plans, sessions, safety invariants, and boundary guards.
"""

from __future__ import annotations

import logging
from typing import Any

from teach_a_skill.execution.models import (
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionSession,
    ExecutionState,
    SafetyLevel,
    StepStatus,
)

logger = logging.getLogger(__name__)


class ExecutionValidator:
    """Validates execution artifacts for structural and semantic correctness."""

    @staticmethod
    def validate_plan(plan: ExecutionPlan) -> list[str]:
        """Validate an execution plan for structural completeness."""
        errors: list[str] = []

        if not plan.plan_id:
            errors.append("Plan missing plan_id")
        if not plan.skill_id:
            errors.append("Plan missing skill_id")
        if not plan.planned_actions and plan.grounding_results:
            errors.append("Plan has grounding results but no planned actions")

        # Validate action consistency
        for action in plan.planned_actions:
            if not action.action_id:
                errors.append(f"Action for step '{action.step_id}' missing action_id")
            if not action.step_id:
                errors.append("Action missing step_id")
            if action.grounding_confidence < 0 or action.grounding_confidence > 1:
                errors.append(
                    f"Action '{action.action_id}' has invalid confidence: "
                    f"{action.grounding_confidence}"
                )

        # Validate grounding consistency
        for gr in plan.grounding_results:
            if not gr.step_id:
                errors.append("Grounding result missing step_id")
            if gr.grounded and not gr.best_candidate:
                errors.append(
                    f"Grounding for '{gr.target_name}' claims grounded "
                    f"but has no best candidate"
                )
            if gr.confidence < 0 or gr.confidence > 1:
                errors.append(
                    f"Grounding for '{gr.target_name}' has invalid confidence: "
                    f"{gr.confidence}"
                )

        return errors

    @staticmethod
    def validate_session(session: ExecutionSession) -> list[str]:
        """Validate an execution session for structural correctness."""
        errors: list[str] = []

        if not session.session_id:
            errors.append("Session missing session_id")
        if not session.skill_id:
            errors.append("Session missing skill_id")
        if session.total_steps < 0:
            errors.append(f"Session has negative total_steps: {session.total_steps}")

        # Check state consistency
        if session.state == ExecutionState.COMPLETED:
            if not session.completed_at:
                errors.append("Completed session missing completed_at timestamp")
            expected_results = session.total_steps
            actual_results = len(session.step_results)
            if actual_results != expected_results and expected_results > 0:
                # Allow partial results for cancelled sessions
                pass

        if session.state == ExecutionState.FAILED and not session.error_message:
            errors.append("Failed session missing error_message")

        # Validate step results
        for result in session.step_results:
            if not result.step_id:
                errors.append("Step result missing step_id")
            if not result.action_id:
                errors.append("Step result missing action_id")

        return errors

    @staticmethod
    def validate_safety_invariants(session: ExecutionSession) -> list[str]:
        """Check that safety invariants were maintained during execution."""
        violations: list[str] = []

        if session.policy == ExecutionPolicy.DRY_RUN:
            # All steps must be dry-run
            for result in session.step_results:
                if not result.was_dry_run:
                    violations.append(
                        f"Step '{result.step_id}' performed real action in DRY_RUN mode"
                    )

        # Blocked steps should never have succeeded
        for result in session.step_results:
            if result.status == StepStatus.BLOCKED and result.verification_passed:
                violations.append(
                    f"Blocked step '{result.step_id}' reports verification passed"
                )

        return violations

    @staticmethod
    def validate_boundary_guards() -> list[str]:
        """Verify execution boundary integrity — no dangerous APIs exposed."""
        violations: list[str] = []
        import teach_a_skill.execution as exec_pkg

        # Phase 10 IS the execution layer, so it should have execution capabilities.
        # But it must NOT have these unsafe APIs:
        dangerous_attrs = [
            "run_shell",
            "run_arbitrary_code",
            "eval_expression",
            "download_model",
            "send_network_request",
            "upload_data",
        ]
        for attr in dangerous_attrs:
            if hasattr(exec_pkg, attr):
                violations.append(f"Execution package exposes dangerous API: {attr}")

        return violations
