"""Deterministic failure classifier for Phase 11.

Analyzes execution evidence, environment snapshots, and action results
to classify failures according to canonical taxonomy, severity, and recoverability.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentSnapshot,
    GroundingResult,
    PlannedAction,
    StepExecutionResult,
    StepStatus,
)
from teach_a_skill.recovery.models import (
    ActionIdempotency,
    FailureRecord,
    FailureSeverity,
    FailureType,
    Recoverability,
    compute_failure_fingerprint,
)
from teach_a_skill.skill.models import SkillStep

logger = logging.getLogger(__name__)

# Action idempotency mapping
IDEMPOTENCY_MAP: dict[ActionType, ActionIdempotency] = {
    ActionType.ACTIVATE_APP: ActionIdempotency.IDEMPOTENT,
    ActionType.ACTIVATE_WINDOW: ActionIdempotency.IDEMPOTENT,
    ActionType.FOCUS: ActionIdempotency.IDEMPOTENT,
    ActionType.NOOP: ActionIdempotency.IDEMPOTENT,
    ActionType.WAIT: ActionIdempotency.IDEMPOTENT,
    ActionType.TYPE_TEXT: ActionIdempotency.CONDITIONALLY_IDEMPOTENT,
    ActionType.SCROLL: ActionIdempotency.CONDITIONALLY_IDEMPOTENT,
    ActionType.CLICK: ActionIdempotency.NON_IDEMPOTENT,
    ActionType.DOUBLE_CLICK: ActionIdempotency.NON_IDEMPOTENT,
    ActionType.RIGHT_CLICK: ActionIdempotency.NON_IDEMPOTENT,
    ActionType.KEY_PRESS: ActionIdempotency.NON_IDEMPOTENT,
    ActionType.KEY_COMBO: ActionIdempotency.NON_IDEMPOTENT,
    ActionType.DRAG: ActionIdempotency.NON_IDEMPOTENT,
}


def classify_action_idempotency(action_type: ActionType) -> ActionIdempotency:
    """Return canonical idempotency classification for a platform action."""
    return IDEMPOTENCY_MAP.get(action_type, ActionIdempotency.UNKNOWN)


class FailureClassifier:
    """Deterministic failure classification engine."""

    def classify_failure(
        self,
        execution_id: str,
        step: Optional[SkillStep],
        action: Optional[PlannedAction],
        step_result: Optional[StepExecutionResult],
        snapshot_before: Optional[EnvironmentSnapshot],
        snapshot_after: Optional[EnvironmentSnapshot],
        grounding: Optional[GroundingResult] = None,
        raw_error: Optional[str] = None,
        skill_version: str = "1.0.0",
    ) -> FailureRecord:
        """Analyze execution failure context and produce a canonical FailureRecord."""
        step_id = step.step_id if step else (action.step_id if action else "unknown_step")
        err_msg = (raw_error or (step_result.error_message if step_result else "")).strip().lower()

        # 1. Security & Policy Violations (Top Priority)
        if any(w in err_msg for w in ("security violation", "blocked_destructive", "dangerous key", "malicious", "privilege")):
            ftype = FailureType.SECURITY_VIOLATION
            severity = FailureSeverity.CRITICAL
            recoverability = Recoverability.NON_RECOVERABLE
            confidence = 1.0
            explanation = f"Critical security constraint triggered: {raw_error or err_msg}"

        elif any(w in err_msg for w in ("policy_denied", "policy rejected", "disallowed action")):
            ftype = FailureType.POLICY_DENIED
            severity = FailureSeverity.HIGH
            recoverability = Recoverability.NON_RECOVERABLE
            confidence = 0.95
            explanation = f"Execution policy prohibited action: {raw_error or err_msg}"

        elif any(w in err_msg for w in ("permission", "unauthorized", "accessibility permission", "access denied")):
            ftype = FailureType.PERMISSION_FAILURE
            severity = FailureSeverity.HIGH
            recoverability = Recoverability.MANUAL_INTERVENTION_REQUIRED
            confidence = 0.9
            explanation = f"OS permission barrier encountered: {raw_error or err_msg}"

        # 2. Timeout Failures
        elif any(w in err_msg for w in ("timeout", "timed out", "deadline exceeded")):
            ftype = FailureType.TIMEOUT
            action_type = action.action_type if action else ActionType.NOOP
            idempotency = classify_action_idempotency(action_type)
            if idempotency == ActionIdempotency.IDEMPOTENT:
                severity = FailureSeverity.RECOVERABLE
                recoverability = Recoverability.AUTOMATICALLY_RECOVERABLE
            else:
                severity = FailureSeverity.HIGH
                recoverability = Recoverability.SUPERVISED_RECOVERABLE
            confidence = 0.9
            explanation = f"Action timed out under {idempotency.value} operation semantics"

        # 3. Environment Context Shifts (Application / Window / Focus)
        elif snapshot_before and snapshot_after and (
            snapshot_before.active_application != snapshot_after.active_application
            and snapshot_after.active_application is not None
        ):
            ftype = FailureType.APPLICATION_CHANGED
            severity = FailureSeverity.HIGH
            recoverability = Recoverability.SUPERVISED_RECOVERABLE
            confidence = 0.85
            explanation = (
                f"Active application unexpectedly shifted from '{snapshot_before.active_application}' "
                f"to '{snapshot_after.active_application}'"
            )

        elif snapshot_before and snapshot_after and (
            snapshot_before.active_window_title != snapshot_after.active_window_title
            and snapshot_after.active_window_title is not None
        ):
            ftype = FailureType.WINDOW_CHANGED
            severity = FailureSeverity.RECOVERABLE
            recoverability = Recoverability.AUTOMATICALLY_RECOVERABLE
            confidence = 0.8
            explanation = (
                f"Active window title changed from '{snapshot_before.active_window_title}' "
                f"to '{snapshot_after.active_window_title}'"
            )

        # 4. Grounding & Target Variations
        elif grounding and grounding.ambiguous:
            ftype = FailureType.AMBIGUOUS_TARGET
            severity = FailureSeverity.HIGH
            recoverability = Recoverability.SUPERVISED_RECOVERABLE
            confidence = 0.85
            explanation = f"Target '{grounding.target_name}' yielded multiple ambiguous candidates"

        elif grounding and not grounding.grounded:
            # Check if loading elements or spinners are present in environment
            has_loading = False
            if snapshot_after:
                for elem in snapshot_after.elements:
                    lbl = (elem.label or elem.title or "").lower()
                    if any(w in lbl for w in ("loading", "busy", "progress", "wait")):
                        has_loading = True
                        break

            if has_loading:
                ftype = FailureType.TEMPORARY_LOADING
                severity = FailureSeverity.RECOVERABLE
                recoverability = Recoverability.AUTOMATICALLY_RECOVERABLE
                confidence = 0.8
                explanation = "Target absent while temporary loading/busy indicator observed"
            else:
                ftype = FailureType.GROUNDING_FAILURE
                severity = FailureSeverity.RECOVERABLE
                recoverability = Recoverability.AUTOMATICALLY_RECOVERABLE
                confidence = 0.75
                explanation = f"Target '{grounding.target_name}' could not be grounded in live snapshot"

        # 5. Precondition & Postcondition Failures
        elif "precondition" in err_msg:
            ftype = FailureType.PRECONDITION_FAILURE
            severity = FailureSeverity.HIGH
            recoverability = Recoverability.MANUAL_INTERVENTION_REQUIRED
            confidence = 0.9
            explanation = f"Precondition failed prior to action: {raw_error or err_msg}"

        elif "verification" in err_msg or "postcondition" in err_msg:
            ftype = FailureType.POSTCONDITION_FAILURE
            severity = FailureSeverity.RECOVERABLE
            recoverability = Recoverability.AUTOMATICALLY_RECOVERABLE
            confidence = 0.85
            explanation = f"Postcondition verification failed: {raw_error or err_msg}"

        # 6. Fallback
        else:
            ftype = FailureType.ACTION_FAILURE
            severity = FailureSeverity.WARNING
            recoverability = Recoverability.AUTOMATICALLY_RECOVERABLE
            confidence = 0.6
            explanation = f"General action failure: {raw_error or err_msg or 'Execution step did not succeed'}"

        # Deterministic failure fingerprint
        env_sig = snapshot_after.snapshot_id if snapshot_after else (snapshot_before.snapshot_id if snapshot_before else "no_env")
        gr_sig = (
            grounding.best_candidate.candidate_id
            if grounding and grounding.best_candidate
            else (grounding.target_name if grounding else "no_target")
        )
        fingerprint = compute_failure_fingerprint(
            skill_version=skill_version,
            step_id=step_id,
            failure_type=ftype,
            environment_signature=env_sig,
            grounding_signature=gr_sig,
        )

        return FailureRecord(
            failure_id=f"fail_{uuid.uuid4().hex[:12]}",
            execution_id=execution_id,
            step_id=step_id,
            failure_type=ftype,
            severity=severity,
            recoverability=recoverability,
            confidence=confidence,
            explanation=explanation,
            evidence={
                "raw_error": raw_error,
                "step_status": step_result.status.value if step_result else None,
                "action_type": action.action_type.value if action else None,
                "grounding_confidence": grounding.confidence if grounding else 0.0,
            },
            failure_fingerprint=fingerprint,
        )
