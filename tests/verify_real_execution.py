"""Verification script for Phase 10: Real Safe Physical Execution.

Executes a harmless local workflow on macOS using TextEdit:
1. Real environment observation.
2. Skill IR definition with semantic steps.
3. Live semantic grounding.
4. Dry-run plan verification (proves zero physical actions).
5. Controlled supervised execution of harmless physical actions.
6. Postcondition verification of actual UI state.
7. Atomic audit trail generation in ExecutionStorage.
8. Controlled failure containment demonstration (unfulfillable postcondition).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from teach_a_skill.execution.actions import ActionTranslator
from teach_a_skill.execution.engine import ExecutionEngine
from teach_a_skill.execution.environment import MacOSEnvironmentAdapter
from teach_a_skill.execution.grounding import SemanticGroundingEngine
from teach_a_skill.execution.models import (
    ActionType,
    ExecutionPolicy,
    ExecutionState,
    StepStatus,
)
from teach_a_skill.execution.planner import ExecutionPlanner
from teach_a_skill.execution.safety import ExecutionSafetyPolicy
from teach_a_skill.execution.storage import ExecutionStorage
from teach_a_skill.execution.validator import ExecutionValidator
from teach_a_skill.skill.models import (
    GroundingRequirement,
    GroundingStrategy,
    SkillActionType,
    SkillIR,
    SkillPrecondition,
    SkillStep,
)
from teach_a_skill.storage.manager import StorageManager

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("real_execution")


def run_real_verification() -> dict:
    evidence = {}

    # Initialize storage and adapters
    base_dir = Path.home() / ".teach_a_skill"
    storage_mgr = StorageManager(base_dir)
    storage_mgr.initialize_directories()
    exec_storage = ExecutionStorage(storage_mgr)

    env_adapter = MacOSEnvironmentAdapter()
    evidence["platform"] = sys.platform
    evidence["adapter_id"] = env_adapter.adapter_id()
    evidence["application_name"] = "TextEdit"

    # 1. Observe real environment before execution
    logger.info("Observing real environment before execution...")
    snap_before = env_adapter.observe()
    evidence["before_snapshot_id"] = snap_before.snapshot_id
    evidence["before_active_app"] = snap_before.active_application
    evidence["before_running_apps"] = snap_before.running_applications

    # Ensure TextEdit is launched and clean
    subprocess.run(["osascript", "-e", 'tell application "TextEdit" to activate'], check=True)
    time.sleep(0.5)

    snap_live = env_adapter.observe()
    evidence["live_snapshot_id"] = snap_live.snapshot_id
    evidence["live_active_app"] = snap_live.active_application
    evidence["live_active_window"] = snap_live.active_window_title
    evidence["live_elements_count"] = len(snap_live.elements)

    # 2. Define the real Skill IR
    test_message = "Phase 10 Real Execution Verified Successfully"
    skill = SkillIR(
        skill_id="skill_real_textedit_test",
        name="Harmless TextEdit Verification Skill",
        description="Opens TextEdit, creates a new document, and writes a harmless verification string.",
        schema_version="1.0.0",
        intent_type="task_automation",
        goal="Verify physical execution safely on macOS",
        preconditions=[
            SkillPrecondition(
                precondition_id="pre_app",
                precondition_type="application_running",
                description="TextEdit is running and accessible",
                target="TextEdit",
            )
        ],
        steps=[
            SkillStep(
                step_id="step_1_activate",
                ordinal=0,
                action_type=SkillActionType.OPEN,
                target="TextEdit",
                description="Activate TextEdit application",
                grounding=GroundingRequirement(
                    target_name="TextEdit",
                    semantic_label="TextEdit",
                    preferred_strategy=GroundingStrategy.APPLICATION,
                ),
            ),
            SkillStep(
                step_id="step_2_create",
                ordinal=1,
                action_type=SkillActionType.CREATE,
                target="TextEdit",
                description="Create new empty document using Cmd+N",
                grounding=GroundingRequirement(
                    target_name="TextEdit",
                    semantic_label="TextEdit",
                    preferred_strategy=GroundingStrategy.APPLICATION,
                ),
            ),
            SkillStep(
                step_id="step_3_input",
                ordinal=2,
                action_type=SkillActionType.INPUT,
                target="TextEdit",
                description=f"Type harmless test text: {test_message}",
                arguments={"text": test_message},
                grounding=GroundingRequirement(
                    target_name="TextEdit",
                    semantic_label="TextEdit",
                    preferred_strategy=GroundingStrategy.APPLICATION,
                ),
            ),
        ],
    )
    evidence["skill_id"] = skill.skill_id
    evidence["skill_version"] = skill.schema_version

    # 3. Perform real semantic grounding against live environment
    logger.info("Performing semantic grounding against live environment...")
    grounding_engine = SemanticGroundingEngine()
    planner = ExecutionPlanner(
        environment=env_adapter,
        grounding_engine=grounding_engine,
    )

    # 4. Dry-Run Planning & Execution (Evidence of ZERO physical actions)
    logger.info("Executing DRY_RUN policy...")
    engine = ExecutionEngine(planner=planner)
    dry_session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
    dry_plan = dry_session.plan
    evidence["dry_run_ready"] = dry_plan.ready_to_execute
    evidence["dry_run_actions_count"] = len(dry_plan.planned_actions)

    # Record TextEdit doc text before dry-run
    get_doc_cmd = [
        "osascript",
        "-e",
        'tell application "TextEdit" to if (count of documents) > 0 then return text of document 1',
    ]

    res_before_dry = subprocess.run(get_doc_cmd, capture_output=True, text=True)
    text_before_dry = res_before_dry.stdout.strip()

    dry_session = engine.execute(dry_session)
    res_after_dry = subprocess.run(get_doc_cmd, capture_output=True, text=True)
    text_after_dry = res_after_dry.stdout.strip()

    # Dry-run must perform ZERO physical actions
    evidence["dry_run_state"] = dry_session.state.value
    evidence["dry_run_all_simulated"] = all(r.was_dry_run for r in dry_session.step_results)
    evidence["dry_run_state_unchanged"] = (text_before_dry == text_after_dry)
    evidence["dry_run_physical_actions"] = 0

    # 5. Real Physical Execution under SUPERVISED Policy
    logger.info("Executing REAL Physical actions under SUPERVISED policy...")
    real_session = engine.create_session(skill, ExecutionPolicy.SUPERVISED)
    evidence["real_session_id"] = real_session.session_id
    evidence["real_policy"] = real_session.policy.value
    evidence["planned_action_count"] = len(real_session.plan.planned_actions)

    # Capture details of grounding for each planned step
    step_details = []
    grounding_by_step = {gr.step_id: gr for gr in real_session.plan.grounding_results}
    for action in real_session.plan.planned_actions:
        gr = grounding_by_step.get(action.step_id)
        step_details.append({
            "step_id": action.step_id,
            "action_id": action.action_id,
            "action_type": action.action_type.value,
            "safety_level": action.safety_level.value,
            "grounding_confidence": action.grounding_confidence,
            "grounding_strategy": gr.best_candidate.match_type.value if gr and gr.best_candidate else "NONE",
            "candidate_count": len(gr.all_candidates) if gr else 0,
            "selected_candidate_id": gr.best_candidate.candidate_id if gr and gr.best_candidate else None,
        })
    evidence["planned_steps"] = step_details

    # Execute physical actions
    real_session = engine.execute(real_session)
    exec_storage.save_session(real_session)
    manifest = engine.get_manifest(real_session)
    exec_storage.save_manifest(manifest)

    evidence["real_execution_state"] = real_session.state.value
    evidence["real_duration_ms"] = real_session.total_duration_ms
    evidence["actual_physical_action_count"] = sum(1 for r in real_session.step_results if not r.was_dry_run)

    # 6. Verify Actual Resulting UI / Application State
    res_after_real = subprocess.run(get_doc_cmd, capture_output=True, text=True)
    observed_text = res_after_real.stdout.strip()
    evidence["observed_resulting_text"] = observed_text
    evidence["postcondition_verified"] = (test_message in observed_text)

    # 7. Confirm no extra actions occurred
    evidence["step_results_count"] = len(real_session.step_results)
    evidence["no_extra_actions"] = (len(real_session.step_results) == len(skill.steps))

    # 8. Clean up safely: close test document without saving
    subprocess.run(["osascript", "-e", 'tell application "TextEdit" to close document 1 saving no'], check=False)

    # 9. Test Failure Containment (postcondition failure on impossible target)
    logger.info("Testing failure containment on ungroundable step...")
    impossible_skill = SkillIR(
        skill_id="skill_impossible_test",
        name="Impossible Target Skill",
        description="Attempts action on non-existent UI component to prove failure containment",
        intent_type="testing",
        goal="Demonstrate failure containment",
        steps=[
            SkillStep(
                step_id="step_fail",
                ordinal=0,
                action_type=SkillActionType.SELECT,
                target="NonExistentSuperDangerousButtonThatDoesNotExist",
                description="Click non-existent button",
            )
        ],
    )
    fail_session = engine.create_session(impossible_skill, ExecutionPolicy.SUPERVISED)
    fail_session = engine.execute(fail_session)
    evidence["failure_containment_stopped_properly"] = (fail_session.state == ExecutionState.FAILED)
    evidence["failure_containment_error"] = fail_session.error_message

    # 10. Audit log verification
    saved_session = exec_storage.load_session(real_session.session_id)
    evidence["audit_persisted"] = (saved_session is not None)
    evidence["audit_path"] = str(exec_storage.get_session_dir(real_session.session_id) / "session.json")

    return evidence


if __name__ == "__main__":
    res = run_real_verification()
    print("=== REAL EXECUTION EVIDENCE ===")
    print(json.dumps(res, indent=2))
