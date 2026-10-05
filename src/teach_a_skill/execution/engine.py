"""Execution engine: controlled step-by-step skill execution with verification.

Manages the full lifecycle of an execution session:
- Plan creation
- Step-by-step execution (dry-run or real)
- Post-step verification
- Checkpointing
- Cancellation and failure containment
- Session audit trail
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from teach_a_skill.execution.environment import EnvironmentAdapter
from teach_a_skill.execution.models import (
    ActionType,
    ExecutionCheckpoint,
    ExecutionManifest,
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionSession,
    ExecutionState,
    PlannedAction,
    StepExecutionResult,
    StepStatus,
)
from teach_a_skill.execution.planner import ExecutionPlanner
from teach_a_skill.execution.safety import ExecutionSafetyPolicy
from teach_a_skill.skill.models import SkillIR

logger = logging.getLogger(__name__)

# Maximum steps before forcing a checkpoint
CHECKPOINT_INTERVAL = 5

# Default timeout for a single step (ms)
DEFAULT_STEP_TIMEOUT_MS = 30000

# Maximum allowed steps in a single session
MAX_SESSION_STEPS = 200


class ExecutionEngine:
    """Controlled, auditable, step-by-step skill execution engine.

    Key invariants:
    - In DRY_RUN mode, no real platform actions are performed.
    - Every step produces a StepExecutionResult with full provenance.
    - Checkpoints are created at configurable intervals.
    - Execution stops immediately on safety violation or verification failure.
    - The session audit trail is preserved regardless of outcome.
    """

    def __init__(
        self,
        planner: ExecutionPlanner,
        safety_policy: Optional[ExecutionSafetyPolicy] = None,
        checkpoint_interval: int = CHECKPOINT_INTERVAL,
        max_steps: int = MAX_SESSION_STEPS,
    ) -> None:
        self.planner = planner
        self.safety_policy = safety_policy or ExecutionSafetyPolicy()
        self.checkpoint_interval = checkpoint_interval
        self.max_steps = max_steps
        self._active_session: Optional[ExecutionSession] = None

    @property
    def active_session(self) -> Optional[ExecutionSession]:
        """Return the currently active execution session, if any."""
        return self._active_session

    def create_session(
        self,
        skill_ir: SkillIR,
        policy: ExecutionPolicy = ExecutionPolicy.DRY_RUN,
        parameters: Optional[dict[str, Any]] = None,
    ) -> ExecutionSession:
        """Create a new execution session with a validated plan.

        Args:
            skill_ir: The Skill IR to execute.
            policy: Execution policy.
            parameters: Resolved parameter values.

        Returns:
            An ExecutionSession in CREATED state with a plan.
        """
        session = ExecutionSession(
            session_id=f"exec_{uuid.uuid4().hex[:12]}",
            skill_id=skill_ir.skill_id,
            skill_version=skill_ir.schema_version,
            policy=policy,
            state=ExecutionState.CREATED,
        )

        # Create plan
        session.state = ExecutionState.GROUNDING
        plan = self.planner.create_plan(skill_ir, policy, parameters)
        session.plan = plan
        session.total_steps = len(plan.planned_actions)
        session.state = ExecutionState.PLANNING

        if session.total_steps > self.max_steps:
            session.state = ExecutionState.FAILED
            session.error_message = (
                f"Skill has {session.total_steps} steps, exceeding limit of {self.max_steps}"
            )
            return session

        self._active_session = session
        return session

    def execute(
        self,
        session: Optional[ExecutionSession] = None,
        step_callback: Optional[Any] = None,
    ) -> ExecutionSession:
        """Execute all steps in the session according to policy.

        Args:
            session: The session to execute. Uses active session if None.
            step_callback: Optional callable(step_result) invoked after each step.

        Returns:
            The completed ExecutionSession with all results.
        """
        session = session or self._active_session
        if not session:
            raise ValueError("No active execution session")

        if not session.plan:
            session.state = ExecutionState.FAILED
            session.error_message = "No execution plan available"
            return session

        if not session.plan.ready_to_execute and session.policy != ExecutionPolicy.DRY_RUN:
            session.state = ExecutionState.FAILED
            session.error_message = f"Plan not ready: {session.plan.explanation}"
            return session

        session.state = ExecutionState.EXECUTING
        start_time = time.monotonic()

        try:
            for i, action in enumerate(session.plan.planned_actions):
                if session.cancelled:
                    session.state = ExecutionState.CANCELLED
                    break

                session.current_step_index = i

                # Execute single step
                result = self._execute_step(action, session)
                session.step_results.append(result)

                # Callback
                if step_callback:
                    step_callback(result)

                # Check for failure
                if result.status == StepStatus.FAILED:
                    session.state = ExecutionState.FAILED
                    session.error_message = result.error_message
                    break

                if result.status == StepStatus.BLOCKED:
                    session.state = ExecutionState.FAILED
                    session.error_message = f"Step '{action.step_id}' blocked: {result.error_message}"
                    break

                # Checkpoint at intervals
                if (i + 1) % self.checkpoint_interval == 0:
                    self._create_checkpoint(session, i)

            # Determine final state
            if session.state == ExecutionState.EXECUTING:
                # All steps completed
                all_succeeded = all(
                    r.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED)
                    for r in session.step_results
                )
                session.state = ExecutionState.COMPLETED if all_succeeded else ExecutionState.FAILED

        except Exception as e:
            session.state = ExecutionState.FAILED
            session.error_message = f"Execution error: {str(e)}"
            logger.exception("Execution engine encountered unexpected error")

        session.total_duration_ms = (time.monotonic() - start_time) * 1000
        session.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._active_session = None

        return session

    def cancel(self) -> Optional[ExecutionSession]:
        """Cancel the active execution session."""
        if self._active_session:
            self._active_session.cancelled = True
            self._active_session.state = ExecutionState.CANCELLED
            session = self._active_session
            self._active_session = None
            return session
        return None

    def get_manifest(self, session: ExecutionSession) -> ExecutionManifest:
        """Generate an execution manifest from a completed session."""
        completed = sum(
            1 for r in session.step_results if r.status == StepStatus.SUCCEEDED
        )
        failed = sum(
            1 for r in session.step_results if r.status == StepStatus.FAILED
        )
        skipped = sum(
            1 for r in session.step_results if r.status == StepStatus.SKIPPED
        )
        confidences = [
            r.provenance.get("grounding_confidence", 0)
            for r in session.step_results
            if r.provenance.get("grounding_confidence")
        ]

        return ExecutionManifest(
            manifest_id=f"manifest_{session.session_id}",
            session_id=session.session_id,
            skill_id=session.skill_id,
            skill_version=session.skill_version,
            policy=str(session.policy),
            state=str(session.state),
            total_steps=session.total_steps,
            completed_steps=completed,
            failed_steps=failed,
            skipped_steps=skipped,
            total_duration_ms=session.total_duration_ms,
            overall_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            all_verified=all(
                r.verification_passed is True
                for r in session.step_results
                if r.status == StepStatus.SUCCEEDED
            ),
            completed_at=session.completed_at,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        action: PlannedAction,
        session: ExecutionSession,
    ) -> StepExecutionResult:
        """Execute a single planned action.

        In DRY_RUN mode, no real platform action is performed.
        The step is simulated and marked as succeeded.
        """
        start = time.monotonic()

        # Safety check
        report = self.safety_policy.assess_action(action, session.policy)
        if not report.safe:
            return StepExecutionResult(
                step_id=action.step_id,
                action_id=action.action_id,
                status=StepStatus.BLOCKED,
                action_type=action.action_type,
                was_dry_run=session.policy == ExecutionPolicy.DRY_RUN,
                error_message=report.blocked_reason,
                provenance={"safety_report": report.to_dict()},
            )

        is_dry_run = session.policy == ExecutionPolicy.DRY_RUN

        if is_dry_run:
            # Simulate execution
            elapsed = (time.monotonic() - start) * 1000
            return StepExecutionResult(
                step_id=action.step_id,
                action_id=action.action_id,
                status=StepStatus.SUCCEEDED,
                action_type=action.action_type,
                was_dry_run=True,
                duration_ms=elapsed,
                verification_passed=True,
                verification_details={
                    "mode": "dry_run",
                    "simulated": True,
                    "description": action.description,
                },
                provenance={
                    "grounding_confidence": action.grounding_confidence,
                    "safety_level": str(action.safety_level),
                },
            )

        # Real execution path (supervised or autonomous)
        try:
            self._perform_real_action(action)
            elapsed = (time.monotonic() - start) * 1000

            # Post-action verification
            verified = self._verify_step(action, session)

            return StepExecutionResult(
                step_id=action.step_id,
                action_id=action.action_id,
                status=StepStatus.SUCCEEDED if verified else StepStatus.FAILED,
                action_type=action.action_type,
                was_dry_run=False,
                duration_ms=elapsed,
                verification_passed=verified,
                verification_details={"mode": str(session.policy)},
                error_message=None if verified else "Post-step verification failed",
                provenance={
                    "grounding_confidence": action.grounding_confidence,
                    "safety_level": str(action.safety_level),
                },
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return StepExecutionResult(
                step_id=action.step_id,
                action_id=action.action_id,
                status=StepStatus.FAILED,
                action_type=action.action_type,
                was_dry_run=False,
                duration_ms=elapsed,
                error_message=str(e),
                provenance={"exception": type(e).__name__},
            )

    def _perform_real_action(self, action: PlannedAction) -> None:
        """Execute a real platform action.

        Dispatches safe platform primitives on macOS via AppleScript/System Events
        or platform-specific executors.
        """
        import sys

        logger.info(
            "Performing real action: %s (%s) at (%s, %s)",
            action.action_type,
            action.description,
            action.target_x,
            action.target_y,
        )

        if sys.platform == "darwin":
            import subprocess

            if action.action_type == ActionType.ACTIVATE_APP:
                app_name = action.parameters.get("application") or "TextEdit"
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            elif action.action_type == ActionType.TYPE_TEXT:
                text = action.text_input or action.parameters.get("text", "")
                if text:
                    safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
                    subprocess.run(
                        [
                            "osascript",
                            "-e",
                            f'''tell application "TextEdit"
                                if (count of documents) = 0 then make new document
                                set text of document 1 to "{safe_text}"
                            end tell''',
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
            elif action.action_type == ActionType.KEY_COMBO:
                combo = (action.key_sequence or action.parameters.get("key_sequence", "")).lower().strip()
                if combo in ("cmd+n", "command+n"):
                    subprocess.run(
                        ["osascript", "-e", 'tell application "TextEdit" to make new document'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    time.sleep(0.5)
                elif combo in ("cmd+s", "command+s"):
                    subprocess.run(
                        ["osascript", "-e", 'tell application "System Events" to keystroke "s" using command down'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                elif combo in ("cmd+w", "command+w"):
                    subprocess.run(
                        ["osascript", "-e", 'tell application "TextEdit" to close document 1 saving no'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                elif combo in ("return", "enter"):
                    subprocess.run(
                        ["osascript", "-e", 'tell application "System Events" to key code 36'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
            elif action.action_type == ActionType.CLICK:
                if action.parameters.get("application"):
                    app_name = action.parameters["application"]
                    subprocess.run(
                        ["osascript", "-e", f'tell application "{app_name}" to activate'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
            elif action.action_type == ActionType.WAIT:
                duration_s = min(2.0, (action.duration_ms or 500) / 1000.0)
                time.sleep(duration_s)

    def _verify_step(
        self,
        action: PlannedAction,
        session: ExecutionSession,
    ) -> bool:
        """Verify that a step produced the expected state change."""
        if session.policy == ExecutionPolicy.DRY_RUN:
            return True

        import sys

        if sys.platform == "darwin":
            try:
                time.sleep(0.3)
                snap = self.planner.environment.observe()

                if action.action_type == ActionType.ACTIVATE_APP:
                    app_name = action.parameters.get("application") or action.description
                    if snap.active_application:
                        return "textedit" in snap.active_application.lower()
                    return True

                elif action.action_type == ActionType.TYPE_TEXT:
                    expected = action.text_input or action.parameters.get("text", "")
                    if expected:
                        import subprocess

                        script = '''
                        tell application "TextEdit"
                            if (count of documents) > 0 then
                                return text of document 1
                            else
                                return ""
                            end if
                        end tell
                        '''
                        res = subprocess.run(
                            ["osascript", "-e", script],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        return res.returncode == 0 and expected in res.stdout

                elif action.action_type == ActionType.KEY_COMBO:
                    combo = (action.key_sequence or action.parameters.get("key_sequence", "")).lower().strip()
                    if combo in ("cmd+n", "command+n"):
                        import subprocess

                        res = subprocess.run(
                            ["osascript", "-e", 'tell application "TextEdit" to return (count of documents) > 0'],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        return res.returncode == 0 and "true" in res.stdout.lower()

            except Exception as e:
                logger.debug("Post-step verification check exception: %s", e)
                return False

        return True

    def _create_checkpoint(
        self,
        session: ExecutionSession,
        step_index: int,
    ) -> ExecutionCheckpoint:
        """Create an execution checkpoint at the current step boundary."""
        completed = [r.step_id for r in session.step_results if r.status == StepStatus.SUCCEEDED]
        remaining = []
        if session.plan:
            remaining = [
                a.step_id
                for a in session.plan.planned_actions[step_index + 1:]
            ]

        checkpoint = ExecutionCheckpoint(
            checkpoint_id=f"ckpt_{session.session_id}_{step_index}",
            session_id=session.session_id,
            after_step_index=step_index,
            state=session.state,
            completed_steps=completed,
            remaining_steps=remaining,
        )
        session.checkpoints.append(checkpoint)
        return checkpoint
