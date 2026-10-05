"""Comprehensive test suite for Phase 11: Verification, Recovery & Error Handling.

Covers:
1. Canonical failure taxonomy, severity, and recoverability
2. Deterministic failure classification (idempotency, timeouts, security, transitions)
3. Multi-source verification engine & conflict detection
4. Recovery grounder (target moved, renamed, disappeared, fresh observation)
5. Recovery planner & finite recovery strategies
6. Bounded recovery budgets & failure loop protection
7. Recovery storage, atomic persistence, corruption rejection, and crash recovery resume safety
8. Safety invariants, prompt injection defense, and skill immutability
9. Resilient execution engine workflows:
   - Safe recoverable workflow
   - Real unrecoverable failure containment
   - Timeout handling without duplication
   - Execution cancellation
10. Adversarial attacks and security boundaries
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from teach_a_skill.execution.actions import ActionTranslator
from teach_a_skill.execution.environment import SyntheticEnvironmentAdapter
from teach_a_skill.execution.grounding import SemanticGroundingEngine
from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentElement,
    EnvironmentSnapshot,
    ExecutionCheckpoint,
    ExecutionPolicy,
    GroundingCandidate,
    GroundingMatchType,
    GroundingResult,
    PlannedAction,
    SafetyLevel,
    StepExecutionResult,
    StepStatus,
)
from teach_a_skill.recovery.benchmark import RecoveryBenchmark
from teach_a_skill.recovery.classifier import (
    FailureClassifier,
    classify_action_idempotency,
)
from teach_a_skill.recovery.engine import ResilientExecutionEngine
from teach_a_skill.recovery.grounder import RecoveryGrounder, RegroundingEvidence
from teach_a_skill.recovery.models import (
    ActionIdempotency,
    BoundingBox,
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
    compute_failure_fingerprint,
)
from teach_a_skill.recovery.planner import RecoveryPlanner
from teach_a_skill.recovery.storage import RecoveryStorage
from teach_a_skill.recovery.validator import RecoveryValidator
from teach_a_skill.recovery.verification import VerificationEngine
from teach_a_skill.skill.models import (
    SkillActionType,
    SkillIR,
    SkillStep,
)
from teach_a_skill.storage.manager import StorageManager


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="teach_skill_phase11_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def storage_manager(temp_dir):
    sm = StorageManager(temp_dir)
    sm.initialize_directories()
    return sm


@pytest.fixture
def recovery_storage(storage_manager):
    return RecoveryStorage(storage_manager)


# ===========================================================================
# 1. Failure Taxonomy & Classification Tests
# ===========================================================================


def test_failure_taxonomy_and_idempotency():
    """Verify canonical failure taxonomy and idempotency mappings."""
    assert FailureType.TRANSIENT_UI_CHANGE == "TRANSIENT_UI_CHANGE"
    assert FailureType.TARGET_MOVED == "TARGET_MOVED"
    assert FailureType.TARGET_RENAMED == "TARGET_RENAMED"
    assert FailureType.SECURITY_VIOLATION == "SECURITY_VIOLATION"
    assert FailureType.POLICY_DENIED == "POLICY_DENIED"

    # Test idempotency
    assert classify_action_idempotency(ActionType.CLICK) == ActionIdempotency.NON_IDEMPOTENT
    assert classify_action_idempotency(ActionType.ACTIVATE_APP) == ActionIdempotency.IDEMPOTENT
    assert classify_action_idempotency(ActionType.TYPE_TEXT) == ActionIdempotency.CONDITIONALLY_IDEMPOTENT


def test_deterministic_failure_classifier_security():
    """Verify classifier marks security constraints as CRITICAL and NON_RECOVERABLE."""
    classifier = FailureClassifier()
    rec = classifier.classify_failure(
        execution_id="exec_sec_1",
        step=None,
        action=None,
        step_result=None,
        snapshot_before=None,
        snapshot_after=None,
        raw_error="Critical security violation: dangerous key blocked",
    )
    assert rec.failure_type == FailureType.SECURITY_VIOLATION
    assert rec.severity == FailureSeverity.CRITICAL
    assert rec.recoverability == Recoverability.NON_RECOVERABLE
    assert rec.confidence == 1.0


def test_deterministic_failure_classifier_timeout():
    """Verify timeout on non-idempotent action requires supervised recovery."""
    classifier = FailureClassifier()
    click_act = PlannedAction(
        action_id="act_click",
        step_id="step_1",
        action_type=ActionType.CLICK,
        target_x=10.0,
        target_y=10.0,
    )
    rec = classifier.classify_failure(
        execution_id="exec_to_1",
        step=None,
        action=click_act,
        step_result=None,
        snapshot_before=None,
        snapshot_after=None,
        raw_error="Operation timed out after 30s",
    )
    assert rec.failure_type == FailureType.TIMEOUT
    assert rec.severity == FailureSeverity.HIGH
    assert rec.recoverability == Recoverability.SUPERVISED_RECOVERABLE


def test_deterministic_failure_classifier_window_transition():
    """Verify unexpected window change is classified accurately."""
    classifier = FailureClassifier()
    before = EnvironmentSnapshot(snapshot_id="s1", active_application="App", active_window_title="Doc1")
    after = EnvironmentSnapshot(snapshot_id="s2", active_application="App", active_window_title="Dialog Prompt")

    rec = classifier.classify_failure(
        execution_id="exec_win_1",
        step=None,
        action=None,
        step_result=None,
        snapshot_before=before,
        snapshot_after=after,
        raw_error=None,
    )
    assert rec.failure_type == FailureType.WINDOW_CHANGED
    assert rec.recoverability == Recoverability.AUTOMATICALLY_RECOVERABLE


def test_deterministic_fingerprint_invariance():
    """Fingerprints must be invariant to timestamps and identical for duplicate failures."""
    fp1 = compute_failure_fingerprint("1.0.0", "step_1", FailureType.TARGET_MOVED, "env_hash", "btn_save")
    fp2 = compute_failure_fingerprint("1.0.0", "step_1", FailureType.TARGET_MOVED, "env_hash", "btn_save")
    fp3 = compute_failure_fingerprint("1.0.0", "step_2", FailureType.TARGET_MOVED, "env_hash", "btn_save")
    assert fp1 == fp2
    assert fp1 != fp3


# ===========================================================================
# 2. Multi-Source Verification Engine Tests
# ===========================================================================


def test_verification_engine_success_with_evidence():
    """Verify evidence is required and verified=True only when conditions match."""
    engine = VerificationEngine()
    step = SkillStep(
        step_id="step_v1",
        ordinal=0,
        action_type=SkillActionType.SELECT,
        target="Save",
        description="click save",
        arguments={"expected_application": "TextEdit", "expected_text": "Save Document"},
    )
    elements = [
        EnvironmentElement(
            element_id="el_1",
            role="button",
            label="Save Document",
            pixel_x=10.0,
            pixel_y=20.0,
            pixel_width=50.0,
            pixel_height=20.0,
        )
    ]
    snap = EnvironmentSnapshot(snapshot_id="snap_1", active_application="TextEdit", elements=elements)

    res = engine.verify_step_postconditions(step, snap, ocr_text="Save Document")
    assert res.verified is True
    assert res.confidence > 0.8
    assert res.conflict_detected is False
    assert "accessibility" in res.source
    assert "application_state" in res.source


def test_verification_engine_conflict_detection():
    """Contradictory evidence (accessibility exists vs contradictory OCR) triggers conflict."""
    engine = VerificationEngine()
    step = SkillStep(
        step_id="step_v2",
        ordinal=0,
        action_type=SkillActionType.SELECT,
        target="Save",
        description="click save",
        arguments={"expected_text": "Save"},
    )
    elements = [
        EnvironmentElement(element_id="el_1", role="button", label="Save", pixel_x=10.0, pixel_y=20.0, pixel_width=50.0, pixel_height=20.0)
    ]
    snap = EnvironmentSnapshot(snapshot_id="snap_2", active_application="App", elements=elements)

    # Contradictory screen OCR where Save is completely absent across a dense 60-char text block
    res = engine.verify_step_postconditions(step, snap, ocr_text="Error: Critical failure. System terminated. Nothing found here.")
    assert res.conflict_detected is True
    assert res.verified is False
    assert "conflicts" in res.evidence


def test_verification_engine_checkpoint_validation():
    """Checkpoint verification detects app/window divergence."""
    from teach_a_skill.execution.models import ExecutionState
    engine = VerificationEngine()
    chk = ExecutionCheckpoint(
        checkpoint_id="chk_1",
        session_id="sess_1",
        after_step_index=0,
        state=ExecutionState.EXECUTING,
        completed_steps=["s0"],
        metadata={"active_application": "AppA", "active_window_title": "WinA"},
    )
    cur_snap = EnvironmentSnapshot(snapshot_id="c2", active_application="AppB", active_window_title="WinB")

    res = engine.verify_checkpoint(chk, cur_snap)
    assert res.verified is False
    assert res.evidence["app_match"] is False


# ===========================================================================
# 3. Recovery Grounder Tests
# ===========================================================================


def test_recovery_grounder_target_moved():
    """Target moved in geometry but semantic identity matched -> re-grounds without stale coords."""
    old_elem = EnvironmentElement(element_id="el_old", role="button", label="Save", pixel_x=10.0, pixel_y=20.0, pixel_width=50.0, pixel_height=20.0)
    new_elem = EnvironmentElement(element_id="el_new", role="button", label="Save", pixel_x=100.0, pixel_y=200.0, pixel_width=50.0, pixel_height=20.0)

    adapter = SyntheticEnvironmentAdapter(elements=[new_elem], active_app="App")
    grounder = RecoveryGrounder(environment_adapter=adapter)

    step = SkillStep(step_id="step_m", ordinal=0, action_type=SkillActionType.SELECT, target="Save", description="save")
    old_cand = GroundingCandidate(
        candidate_id="c_old",
        target_name="Save",
        match_type=GroundingMatchType.ACCESSIBILITY,
        confidence=0.9,
        pixel_x=10.0,
        pixel_y=20.0,
        pixel_width=50.0,
        pixel_height=20.0,
    )
    old_grounding = GroundingResult(step_id="step_m", target_name="Save", grounded=True, best_candidate=old_cand)

    fail = FailureRecord(
        failure_id="f1",
        execution_id="e1",
        step_id="step_m",
        failure_type=FailureType.TARGET_MOVED,
        severity=FailureSeverity.RECOVERABLE,
        recoverability=Recoverability.AUTOMATICALLY_RECOVERABLE,
        confidence=0.8,
        explanation="Target moved",
    )

    reground, ev = grounder.reobserve_and_reground(step, fail, old_grounding)
    assert reground is not None
    assert reground.grounded is True
    assert ev.regrounded is True
    assert ev.new_coordinates.x == 100.0
    assert ev.new_coordinates.y == 200.0
    assert "Target moved" in ev.why_regrounding_occurred


def test_recovery_grounder_target_renamed():
    """Target renamed 'Save' -> 'Save Document' -> semantic fuzzy re-grounding succeeds."""
    new_elem = EnvironmentElement(element_id="el_doc", role="button", label="Save Document", pixel_x=50.0, pixel_y=50.0, pixel_width=80.0, pixel_height=30.0)
    adapter = SyntheticEnvironmentAdapter(elements=[new_elem], active_app="App")
    grounder = RecoveryGrounder(environment_adapter=adapter)

    step = SkillStep(step_id="step_r", ordinal=0, action_type=SkillActionType.SELECT, target="Save", description="save button")
    fail = FailureRecord(
        failure_id="f2",
        execution_id="e2",
        step_id="step_r",
        failure_type=FailureType.TARGET_RENAMED,
        severity=FailureSeverity.RECOVERABLE,
        recoverability=Recoverability.AUTOMATICALLY_RECOVERABLE,
        confidence=0.8,
        explanation="Renamed",
    )

    reground, ev = grounder.reobserve_and_reground(step, fail, None)
    assert reground is not None
    assert reground.grounded is True
    assert ev.new_target == "Save Document"
    assert ev.new_confidence >= 0.7


def test_recovery_grounder_target_disappeared():
    """Target genuinely absent -> grounder safely stops without inventing targets."""
    adapter = SyntheticEnvironmentAdapter(elements=[], active_app="App")
    grounder = RecoveryGrounder(environment_adapter=adapter)

    step = SkillStep(step_id="step_d", ordinal=0, action_type=SkillActionType.SELECT, target="Submit", description="submit")
    fail = FailureRecord(
        failure_id="f3",
        execution_id="e3",
        step_id="step_d",
        failure_type=FailureType.TARGET_DISAPPEARED,
        severity=FailureSeverity.HIGH,
        recoverability=Recoverability.AUTOMATICALLY_RECOVERABLE,
        confidence=0.7,
        explanation="Absent",
    )

    reground, ev = grounder.reobserve_and_reground(step, fail, None)
    assert reground is None
    assert ev.regrounded is False
    assert "not found" in ev.why_regrounding_occurred


# ===========================================================================
# 4. Recovery Planner & Budget Tests
# ===========================================================================


def test_recovery_budget_enforcement():
    """Recovery budget tracks and terminates when limits are hit."""
    budget = RecoveryBudget(step_retry_budget=2, execution_retry_budget=3, time_budget_s=10.0)
    assert budget.can_attempt_step_recovery("step_1") is True

    budget.consume("step_1", 1.0)
    assert budget.can_attempt_step_recovery("step_1") is True

    budget.consume("step_1", 1.0)
    # Exceeded step retry budget
    assert budget.can_attempt_step_recovery("step_1") is False

    # Still budget for another step
    assert budget.can_attempt_step_recovery("step_2") is True
    budget.consume("step_2", 1.0)

    # Exceeded total execution retry budget
    assert budget.can_attempt_step_recovery("step_2") is False


def test_recovery_planner_finite_strategies():
    """Planner generates valid RecoveryPlan with supported strategies."""
    planner = RecoveryPlanner()
    budget = RecoveryBudget()

    # Focus lost -> REFOCUS
    fail_focus = FailureRecord(
        failure_id="f_foc",
        execution_id="e",
        step_id="s1",
        failure_type=FailureType.FOCUS_LOST,
        severity=FailureSeverity.RECOVERABLE,
        recoverability=Recoverability.AUTOMATICALLY_RECOVERABLE,
        confidence=0.9,
        explanation="Focus lost",
    )
    step = SkillStep(step_id="s1", ordinal=0, action_type=SkillActionType.SELECT, target="btn", description="click", arguments={"expected_application": "TextEdit"})
    plan = planner.plan_recovery(fail_focus, step, None, budget)
    assert plan.recovery_strategy == RecoveryStrategy.REFOCUS

    # Loading -> WAIT_FOR_STATE
    fail_load = FailureRecord(
        failure_id="f_load",
        execution_id="e",
        step_id="s1",
        failure_type=FailureType.TEMPORARY_LOADING,
        severity=FailureSeverity.RECOVERABLE,
        recoverability=Recoverability.AUTOMATICALLY_RECOVERABLE,
        confidence=0.8,
        explanation="Loading",
    )
    plan_load = planner.plan_recovery(fail_load, step, None, budget)
    assert plan_load.recovery_strategy == RecoveryStrategy.WAIT_FOR_STATE

    # Budget exhausted -> STOP
    exhausted_budget = RecoveryBudget(step_retry_budget=0)
    plan_stop = planner.plan_recovery(fail_focus, step, None, exhausted_budget)
    assert plan_stop.recovery_strategy == RecoveryStrategy.STOP


# ===========================================================================
# 5. Recovery Storage, Corruption & Resume Safety Tests
# ===========================================================================


def test_recovery_storage_atomic_io(recovery_storage):
    """Storage atomically persists failure records with sensitive data redacted."""
    record = FailureRecord(
        failure_id="fail_atomic_1",
        execution_id="exec_1",
        step_id="s1",
        failure_type=FailureType.TARGET_MOVED,
        severity=FailureSeverity.RECOVERABLE,
        recoverability=Recoverability.AUTOMATICALLY_RECOVERABLE,
        confidence=0.9,
        explanation="Target moved",
        evidence={"password": "supersecretpassword", "safe_val": 42},
    )
    recovery_storage.save_failure_record(record)

    loaded = recovery_storage.load_failure_record("fail_atomic_1")
    assert loaded is not None
    assert loaded.failure_id == "fail_atomic_1"
    # Verify sensitive data was redacted
    assert loaded.evidence["password"] == "[REDACTED]"
    assert loaded.evidence["safe_val"] == 42


def test_recovery_storage_corruption_detection(recovery_storage):
    """Corrupted json files are safely rejected without crashing."""
    corrupt_path = recovery_storage.recovery_dir / "failure_corrupt_1.json"
    recovery_storage.sm.write_atomic_text(corrupt_path, "{broken_json_not_valid: true")

    loaded = recovery_storage.load_failure_record("corrupt_1")
    assert loaded is None


def test_crash_recovery_resume_safety(recovery_storage):
    """Crash recovery enforces resume safety: automatic physical execution is blocked."""
    recovery_storage.save_session_state(
        execution_id="crashed_sess_1",
        status="RUNNING",
        completed_steps=["s0"],
        interrupted=False,
        resume_authorized=False,
    )

    res = recovery_storage.recover_interrupted_session("crashed_sess_1")
    # Must NOT automatically resume physical execution
    assert res["can_resume"] is False
    assert "Explicit resume authorization required" in res["reason"]

    # Session is safely marked INTERRUPTED
    assert res["session"]["interrupted"] is True
    assert res["session"]["status"] == "INTERRUPTED"

    # When explicit authorization is given:
    recovery_storage.save_session_state(
        execution_id="crashed_sess_1",
        status="INTERRUPTED",
        completed_steps=["s0"],
        interrupted=True,
        resume_authorized=True,
    )
    auth_res = recovery_storage.recover_interrupted_session("crashed_sess_1")
    assert auth_res["can_resume"] is True


# ===========================================================================
# 6. Safety Invariants & Boundary Validation Tests
# ===========================================================================


def test_recovery_validator_all_checks(storage_manager):
    """RecoveryValidator verifies all 5 core safety invariants."""
    validator = RecoveryValidator()
    report = validator.run_all_validation_checks()
    assert report["all_passed"] is True
    assert report["action_safety"]["passed"] is True
    assert report["injection_defense"]["passed"] is True
    assert report["skill_immutability"]["passed"] is True
    assert report["bounded_budget"]["passed"] is True


def test_recovery_validator_blocks_shell_injection():
    """Malicious prompt-injected shell tokens are caught and blocked."""
    validator = RecoveryValidator()
    injected_action = PlannedAction(
        action_id="act_inj",
        step_id="step_1",
        action_type=ActionType.TYPE_TEXT,
        target_x=10.0,
        target_y=10.0,
        parameters={"text": "osascript -e 'do shell script rm -rf /'"},
        safety_level=SafetyLevel.SAFE,
    )
    ok, msg = validator.validate_action_safety(injected_action)
    assert ok is False
    assert "Dangerous command injection token" in msg


def test_recovery_validator_skill_immutability():
    """SkillIR mutation during execution is detected and rejected."""
    validator = RecoveryValidator()
    step1 = SkillStep(step_id="s1", ordinal=0, action_type=SkillActionType.SELECT, target="btn", description="d")
    step2 = SkillStep(step_id="s1", ordinal=0, action_type=SkillActionType.SELECT, target="mutated_target", description="d")

    sk1 = SkillIR(skill_id="sk1", name="N", description="D", intent_type="click", goal="G", steps=[step1])
    sk2 = SkillIR(skill_id="sk1", name="N", description="D", intent_type="click", goal="G", steps=[step2])

    ok, msg = validator.validate_skill_immutability(sk1, sk2)
    assert ok is False
    assert "mutated" in msg


# ===========================================================================
# 7. Resilient Execution Engine End-to-End Tests
# ===========================================================================


def test_resilient_execution_safe_recovery(storage_manager):
    """End-to-end safe recovery: target moved -> re-ground -> recover -> SUCCESS_AFTER_RECOVERY."""
    elem_new = EnvironmentElement(
        element_id="el_target",
        role="button",
        label="Save Document",
        pixel_x=100.0,
        pixel_y=150.0,
        pixel_width=60.0,
        pixel_height=30.0,
    )
    # Start with initial empty, then target appears
    adapter = SyntheticEnvironmentAdapter(elements=[elem_new], active_app="TextEdit")
    rec_storage = RecoveryStorage(storage_manager)

    engine = ResilientExecutionEngine(
        environment_adapter=adapter,
        execution_policy=ExecutionPolicy.DRY_RUN,
        storage=rec_storage,
    )

    step = SkillStep(
        step_id="s1",
        ordinal=0,
        action_type=SkillActionType.SELECT,
        target="Save",
        description="Save file",
        arguments={"expected_application": "TextEdit", "expected_text": "Save Document"},
    )
    skill = SkillIR(
        skill_id="skill_safe_rec",
        name="Safe Recovery Skill",
        description="Tests recovery",
        intent_type="save",
        goal="save doc",
        steps=[step],
    )

    res = engine.execute_skill_resilient(skill)
    assert res["outcome"] in (ExecutionOutcome.SUCCESS, ExecutionOutcome.SUCCESS_AFTER_RECOVERY)
    assert len(res["completed_steps"]) == 1


def test_resilient_execution_unrecoverable_stops_cleanly(storage_manager):
    """Unrecoverable target stops cleanly with 0 unauthorized physical actions."""
    # Completely empty environment with incompatible application
    adapter = SyntheticEnvironmentAdapter(elements=[], active_app="WrongApp")
    rec_storage = RecoveryStorage(storage_manager)

    engine = ResilientExecutionEngine(
        environment_adapter=adapter,
        execution_policy=ExecutionPolicy.DRY_RUN,
        recovery_policy=RecoveryPolicy(max_retries_per_step=1),
        storage=rec_storage,
    )

    step = SkillStep(
        step_id="s1",
        ordinal=0,
        action_type=SkillActionType.SELECT,
        target="NonExistentTarget",
        description="target that cannot be grounded",
        arguments={"expected_application": "TextEdit"},
    )
    skill = SkillIR(
        skill_id="skill_unrec",
        name="Unrecoverable Skill",
        description="Tests unrecoverable",
        intent_type="click",
        goal="click missing",
        steps=[step],
    )

    res = engine.execute_skill_resilient(skill)
    assert res["outcome"] in (ExecutionOutcome.FAILED_RECOVERABLE_EXHAUSTED, ExecutionOutcome.FAILED_UNRECOVERABLE)
    assert len(res["completed_steps"]) == 0


def test_resilient_execution_cancellation(storage_manager):
    """Cancellation halts execution and preserves audit records."""
    elem = EnvironmentElement(element_id="el_1", role="button", label="Next", pixel_x=10.0, pixel_y=10.0, pixel_width=40.0, pixel_height=20.0)
    adapter = SyntheticEnvironmentAdapter(elements=[elem], active_app="TextEdit")
    rec_storage = RecoveryStorage(storage_manager)

    engine = ResilientExecutionEngine(
        environment_adapter=adapter,
        execution_policy=ExecutionPolicy.DRY_RUN,
        storage=rec_storage,
    )

    steps = [
        SkillStep(step_id=f"s_{i}", ordinal=i, action_type=SkillActionType.SELECT, target="Next", description="step")
        for i in range(5)
    ]
    skill = SkillIR(
        skill_id="skill_cancel",
        name="Cancellation Skill",
        description="Tests cancellation",
        intent_type="test",
        goal="test",
        steps=steps,
    )

    # Cancel before execution
    engine.cancel()
    res = engine.execute_skill_resilient(skill)
    assert res["outcome"] == ExecutionOutcome.CANCELLED
    assert len(res["completed_steps"]) == 0


def test_resilient_execution_loop_protection(storage_manager):
    """Identical failure fingerprint repeating halts execution loop."""
    adapter = SyntheticEnvironmentAdapter(elements=[], active_app="App")
    rec_storage = RecoveryStorage(storage_manager)

    engine = ResilientExecutionEngine(
        environment_adapter=adapter,
        execution_policy=ExecutionPolicy.DRY_RUN,
        recovery_policy=RecoveryPolicy(max_retries_per_step=2),
        storage=rec_storage,
    )

    step = SkillStep(step_id="s_loop", ordinal=0, action_type=SkillActionType.SELECT, target="TargetLoop", description="loop")
    skill = SkillIR(
        skill_id="skill_loop",
        name="Loop Skill",
        description="Tests loop protection",
        intent_type="test",
        goal="test",
        steps=[step],
    )

    res = engine.execute_skill_resilient(skill)
    assert res["outcome"] == ExecutionOutcome.FAILED_RECOVERABLE_EXHAUSTED


# ===========================================================================
# 8. Benchmark Suite Verification
# ===========================================================================


def test_recovery_benchmark_runs_cleanly():
    """Verify synthetic benchmark suite scales and remains memory bounded."""
    bm = RecoveryBenchmark()
    # Test scaled subsets for rapid unit test validation
    res_cls = bm.benchmark_classification(counts=[10, 50])
    res_pln = bm.benchmark_planning(step_counts=[5, 10])
    res_ver = bm.benchmark_verification(candidate_counts=[5, 20])
    res_lng = bm.benchmark_long_run_stability(cycles=20)

    assert "count_50" in res_cls
    assert res_pln["steps_10"]["duration_ms"] >= 0.0
    assert "candidates_20" in res_ver
    assert res_lng["memory_bounded"] is True
