"""Resilient execution engine for Phase 11.

Executes skills with integrated multi-source verification, failure classification,
bounded recovery planning, safe re-grounding, checkpoint restoration,
and strict loop protection.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Optional

from teach_a_skill.execution.actions import ActionTranslator
from teach_a_skill.execution.engine import ExecutionEngine
from teach_a_skill.execution.environment import (
    EnvironmentAdapter,
    LocalEnvironmentAdapter,
    get_environment_adapter,
)
from teach_a_skill.execution.grounding import SemanticGroundingEngine
from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentSnapshot,
    ExecutionCheckpoint,
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionSession,
    ExecutionState,
    GroundingResult,
    PlannedAction,
    SafetyLevel,
    StepExecutionResult,
    StepStatus,
)
from teach_a_skill.execution.planner import ExecutionPlanner
from teach_a_skill.execution.safety import ExecutionSafetyPolicy
from teach_a_skill.recovery.classifier import FailureClassifier
from teach_a_skill.recovery.grounder import RecoveryGrounder
from teach_a_skill.recovery.models import (
    ActionIdempotency,
    ExecutionOutcome,
    FailureRecord,
    FailureSeverity,
    FailureType,
    Recoverability,
    RecoveryAttempt,
    RecoveryBudget,
    RecoveryPlan,
    RecoveryPolicy,
    RecoveryStrategy,
    VerificationResult,
)
from teach_a_skill.recovery.planner import RecoveryPlanner
from teach_a_skill.recovery.storage import RecoveryStorage
from teach_a_skill.recovery.verification import VerificationEngine
from teach_a_skill.skill.models import SkillIR, SkillStep

logger = logging.getLogger(__name__)


class ResilientExecutionEngine:
    """Manages the Phase 11 resilient execution and recovery loop."""

    def __init__(
        self,
        environment_adapter: Optional[EnvironmentAdapter] = None,
        execution_policy: Optional[ExecutionPolicy] = None,
        recovery_policy: Optional[RecoveryPolicy] = None,
        storage: Optional[RecoveryStorage] = None,
    ) -> None:
        self.adapter = environment_adapter or get_environment_adapter()
        self.policy = execution_policy or ExecutionPolicy.DRY_RUN
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self.storage = storage or RecoveryStorage()

        self.grounding_engine = SemanticGroundingEngine()
        self.translator = ActionTranslator()
        self.safety_policy = ExecutionSafetyPolicy()
        self.planner = ExecutionPlanner(
            environment=self.adapter,
            grounding_engine=self.grounding_engine,
            action_translator=self.translator,
            safety_policy=self.safety_policy,
        )
        self.exec_engine = ExecutionEngine(
            planner=self.planner,
            safety_policy=self.safety_policy,
        )

        self.verifier = VerificationEngine()
        self.classifier = FailureClassifier()
        self.grounder = RecoveryGrounder(
            environment_adapter=self.adapter,
            base_grounder=self.grounding_engine,
            policy=self.recovery_policy,
        )
        self.rec_planner = RecoveryPlanner(policy=self.recovery_policy)

        # Runtime state
        self._cancelled = False
        self._checkpoints: dict[str, ExecutionCheckpoint] = {}
        self._fingerprint_counts: dict[str, int] = {}

    def cancel(self) -> None:
        """Signal immediate execution cancellation."""
        self._cancelled = True
        self.exec_engine.cancel()
        logger.info("Resilient execution cancellation requested")

    def execute_skill_resilient(
        self,
        skill: SkillIR,
        policy: Optional[ExecutionPolicy] = None,
        confirmation_callback: Optional[Callable[[str], bool]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a skill with closed-loop verification, bounded recovery, and audit tracking."""
        exec_policy = policy or self.policy
        session_id = f"exec_{uuid.uuid4().hex[:12]}"
        budget = RecoveryBudget(
            step_retry_budget=self.recovery_policy.max_retries_per_step,
            execution_retry_budget=self.recovery_policy.max_total_recovery_attempts,
            time_budget_s=self.recovery_policy.max_recovery_duration_s,
        )
        completed_step_ids: list[str] = []
        failure_records: list[FailureRecord] = []
        recovery_attempts: list[RecoveryAttempt] = []
        outcome = ExecutionOutcome.SUCCESS
        had_recovery = False

        if not self._cancelled:
            self._cancelled = False
        self._fingerprint_counts.clear()
        self._checkpoints.clear()

        # Session tracking
        session = ExecutionSession(
            session_id=session_id,
            skill_id=skill.skill_id,
            skill_version=skill.version if hasattr(skill, "version") else skill.schema_version,
            policy=exec_policy,
            state=ExecutionState.EXECUTING,
            total_steps=len(skill.steps),
        )

        self.storage.save_session_state(
            execution_id=session_id,
            status="RUNNING",
            completed_steps=completed_step_ids,
        )

        steps = skill.steps
        step_idx = 0

        while step_idx < len(steps):
            if self._cancelled:
                outcome = ExecutionOutcome.CANCELLED
                break

            step = steps[step_idx]
            step_id = step.step_id
            self.storage.save_session_state(
                execution_id=session_id,
                status="RUNNING",
                completed_steps=completed_step_ids,
                current_step_id=step_id,
            )

            # Observe state before action
            snapshot_before = self.adapter.observe()

            # Ground target
            grounding = self.grounding_engine.ground_step(step, snapshot_before)

            # Translate step to planned action
            action = self.translator.translate_step(step, grounding, parameters)

            # Execute action through execution engine
            step_result = self.exec_engine._execute_step(action, session)

            # Fresh observation after execution
            snapshot_after = self.adapter.observe()

            # Multi-source postcondition verification
            verification = self.verifier.verify_step_postconditions(
                step=step,
                snapshot=snapshot_after,
            )

            # Check if succeeded
            if step_result.status == StepStatus.SUCCEEDED and verification.verified:
                completed_step_ids.append(step_id)
                chk = ExecutionCheckpoint(
                    checkpoint_id=f"chk_{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    after_step_index=step_idx,
                    state=ExecutionState.EXECUTING,
                    completed_steps=list(completed_step_ids),
                )
                self._checkpoints[step_id] = chk
                self.storage.save_checkpoint(chk)
                step_idx += 1
                continue

            # Step failed or verification failed -> initiate Phase 11 recovery sequence
            raw_err = step_result.error_message
            if not raw_err and not verification.verified:
                raw_err = f"Verification postconditions failed (confidence={verification.confidence:.2f})"

            # 1. Deterministic Failure Classification
            failure = self.classifier.classify_failure(
                execution_id=session_id,
                step=step,
                action=action,
                step_result=step_result,
                snapshot_before=snapshot_before,
                snapshot_after=snapshot_after,
                grounding=grounding,
                raw_error=raw_err,
                skill_version=skill.version if hasattr(skill, "version") else skill.schema_version,
            )
            failure_records.append(failure)
            self.storage.save_failure_record(failure)

            # Loop Protection: fingerprint repetition limit
            fp = failure.failure_fingerprint
            self._fingerprint_counts[fp] = self._fingerprint_counts.get(fp, 0) + 1
            if self._fingerprint_counts[fp] > self.recovery_policy.max_retries_per_step:
                logger.warning("Recovery loop protection triggered on fingerprint %s", fp)
                outcome = ExecutionOutcome.FAILED_RECOVERABLE_EXHAUSTED
                break

            # 2. Check Unrecoverable or Security Failures
            if failure.severity == FailureSeverity.CRITICAL or failure.recoverability == Recoverability.NON_RECOVERABLE:
                if failure.failure_type == FailureType.SECURITY_VIOLATION:
                    outcome = ExecutionOutcome.FAILED_SECURITY
                elif failure.failure_type == FailureType.POLICY_DENIED:
                    outcome = ExecutionOutcome.FAILED_POLICY
                else:
                    outcome = ExecutionOutcome.FAILED_UNRECOVERABLE
                break

            # 3. Formulate Recovery Plan
            plan = self.rec_planner.plan_recovery(
                failure=failure,
                step=step,
                last_action=action,
                budget=budget,
            )
            self.storage.save_recovery_plan(plan)

            if plan.recovery_strategy == RecoveryStrategy.STOP:
                outcome = (
                    ExecutionOutcome.FAILED_RECOVERABLE_EXHAUSTED
                    if "budget" in plan.explanation.lower()
                    else ExecutionOutcome.FAILED_UNRECOVERABLE
                )
                break

            if plan.recovery_strategy == RecoveryStrategy.ESCALATE:
                outcome = ExecutionOutcome.USER_ABORTED
                break

            # 4. Confirmation Gate (if policy requires confirmation)
            if plan.recovery_strategy in self.recovery_policy.require_confirmation_for:
                if confirmation_callback:
                    confirmed = confirmation_callback(plan.explanation)
                    if not confirmed:
                        outcome = ExecutionOutcome.USER_ABORTED
                        break
                else:
                    outcome = ExecutionOutcome.USER_ABORTED
                    break

            # 5. Execute Recovery Strategy
            had_recovery = True
            rec_start_time = time.time()
            recovery_success = False
            rec_action: Optional[PlannedAction] = None
            rec_err: Optional[str] = None

            if plan.recovery_strategy == RecoveryStrategy.WAIT_FOR_STATE:
                time.sleep(0.5)
                fresh_snap = self.adapter.observe()
                ver_check = self.verifier.verify_step_postconditions(step, fresh_snap)
                recovery_success = ver_check.verified

            elif plan.recovery_strategy in (RecoveryStrategy.REGROUND, RecoveryStrategy.REOBSERVE):
                reground_res, evidence = self.grounder.reobserve_and_reground(
                    step=step,
                    failure=failure,
                    old_grounding=grounding,
                )
                if reground_res and reground_res.grounded:
                    rec_action = self.translator.translate_step(step, reground_res, parameters)
                    report = self.safety_policy.assess_action(rec_action, exec_policy)
                    if report.safe:
                        res = self.exec_engine._execute_step(rec_action, session)
                        fresh_snap = self.adapter.observe()
                        ver_check = self.verifier.verify_step_postconditions(step, fresh_snap)
                        recovery_success = res.status == StepStatus.SUCCEEDED and ver_check.verified
                    else:
                        rec_err = f"Safety policy rejected recovery action: {report.blocked_reason}"
                else:
                    rec_err = evidence.why_regrounding_occurred

            elif plan.recovery_strategy == RecoveryStrategy.REFOCUS:
                if plan.candidate_actions:
                    rec_action = plan.candidate_actions[0]
                    res = self.exec_engine._execute_step(rec_action, session)
                    fresh_snap = self.adapter.observe()
                    recovery_success = res.status == StepStatus.SUCCEEDED

            elif plan.recovery_strategy == RecoveryStrategy.RETRY_IDEMPOTENT:
                if plan.candidate_actions:
                    rec_action = plan.candidate_actions[0]
                    res = self.exec_engine._execute_step(rec_action, session)
                    fresh_snap = self.adapter.observe()
                    ver_check = self.verifier.verify_step_postconditions(step, fresh_snap)
                    recovery_success = res.status == StepStatus.SUCCEEDED and ver_check.verified

            rec_duration = (time.time() - rec_start_time) * 1000.0
            budget.consume(step_id=step_id, elapsed_s=rec_duration / 1000.0, action_cost=1, risk_cost=1)

            # Persist recovery attempt audit record
            attempt = RecoveryAttempt(
                attempt_id=f"att_{uuid.uuid4().hex[:8]}",
                failure_id=failure.failure_id,
                strategy=plan.recovery_strategy,
                before_state={"snapshot_id": snapshot_before.snapshot_id if snapshot_before else None},
                action=rec_action,
                after_state={"snapshot_id": snapshot_after.snapshot_id if snapshot_after else None},
                verification_passed=recovery_success,
                result="RECOVERED" if recovery_success else "FAILED",
                confidence=plan.confidence,
                risk=plan.risk,
                duration_ms=rec_duration,
                error_message=rec_err,
            )
            recovery_attempts.append(attempt)
            self.storage.save_recovery_attempt(attempt)

            if recovery_success:
                completed_step_ids.append(step_id)
                step_idx += 1
            else:
                if not budget.can_attempt_step_recovery(step_id):
                    outcome = ExecutionOutcome.FAILED_RECOVERABLE_EXHAUSTED
                    break

        if outcome == ExecutionOutcome.SUCCESS and had_recovery:
            outcome = ExecutionOutcome.SUCCESS_AFTER_RECOVERY

        final_status = "COMPLETED" if outcome in (ExecutionOutcome.SUCCESS, ExecutionOutcome.SUCCESS_AFTER_RECOVERY) else "FAILED"
        self.storage.save_session_state(
            execution_id=session_id,
            status=final_status,
            completed_steps=completed_step_ids,
        )

        return {
            "execution_id": session_id,
            "outcome": outcome,
            "completed_steps": completed_step_ids,
            "total_steps": len(steps),
            "failures": [f.to_dict() for f in failure_records],
            "recovery_attempts": [a.to_dict() for a in recovery_attempts],
            "budget": budget.to_dict(),
        }
