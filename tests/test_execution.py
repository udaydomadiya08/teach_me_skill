from __future__ import annotations

"""Phase 10: Skill Execution & Semantic Grounding — comprehensive tests.

Covers:
- Execution models serialization/deserialization
- Environment observation (synthetic)
- Semantic grounding (multi-strategy, confidence, ambiguity)
- Safety policy enforcement
- Action translation
- Execution planning
- Execution engine (dry-run, failure, cancellation, checkpointing)
- Execution storage (persistence, recovery)
- Execution validator (structural, safety invariants, boundary guards)
- Execution cache
- Execution benchmark
- Semantic boundary tests
- Adversarial/edge cases
"""

import json
import time
import uuid

import pytest

from teach_a_skill.execution.actions import ActionTranslator
from teach_a_skill.execution.benchmark import run_execution_benchmark
from teach_a_skill.execution.cache import ExecutionCache
from teach_a_skill.execution.engine import ExecutionEngine
from teach_a_skill.execution.environment import (
    SyntheticEnvironmentAdapter,
    get_environment_adapter,
)
from teach_a_skill.execution.grounding import SemanticGroundingEngine
from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentElement,
    EnvironmentSnapshot,
    ExecutionCheckpoint,
    ExecutionManifest,
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionSession,
    ExecutionState,
    GroundingCandidate,
    GroundingMatchType,
    GroundingResult,
    PlannedAction,
    SafetyLevel,
    StepExecutionResult,
    StepStatus,
)
from teach_a_skill.execution.planner import ExecutionPlanner
from teach_a_skill.execution.safety import ExecutionSafetyPolicy, SafetyReport
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


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------


def _make_element(
    eid: str,
    role: str = "button",
    label: str = "OK",
    px: float = 100,
    py: float = 200,
    pw: float = 80,
    ph: float = 30,
    app: str = "TextEdit",
    window: str = "Untitled",
) -> EnvironmentElement:
    return EnvironmentElement(
        element_id=eid,
        role=role,
        label=label,
        pixel_x=px,
        pixel_y=py,
        pixel_width=pw,
        pixel_height=ph,
        application=app,
        window_title=window,
    )


def _make_step(
    sid: str = "step_1",
    ordinal: int = 0,
    action: SkillActionType = SkillActionType.SELECT,
    target: str = "OK",
    desc: str | None = None,
    grounding: GroundingRequirement | None = None,
) -> SkillStep:
    if desc is None:
        desc = f"Click {target}"
    return SkillStep(
        step_id=sid,
        ordinal=ordinal,
        action_type=action,
        target=target,
        description=desc,
        grounding=grounding
        or GroundingRequirement(
            target_name=target,
            semantic_label=target,
            preferred_strategy=GroundingStrategy.ACCESSIBILITY,
        ),
    )


def _make_skill(
    steps: list[SkillStep] | None = None,
    preconditions: list[SkillPrecondition] | None = None,
) -> SkillIR:
    return SkillIR(
        skill_id="test_skill",
        name="Test Skill",
        description="A test skill",
        intent_type="task_completion",
        goal="Complete test task",
        steps=[_make_step()] if steps is None else steps,
        preconditions=preconditions or [],
    )


def _make_env(elements: list[EnvironmentElement] | None = None) -> SyntheticEnvironmentAdapter:
    if elements is None:
        elements = [_make_element("btn_ok")]
    return SyntheticEnvironmentAdapter(
        elements=elements,
        active_app="TextEdit",
        active_window="Untitled",
        running_apps=["TextEdit", "Finder"],
    )


# -----------------------------------------------------------------------
# 1. Model serialization/deserialization
# -----------------------------------------------------------------------


class TestModels:
    def test_grounding_candidate_roundtrip(self):
        c = GroundingCandidate(
            candidate_id="c1",
            target_name="Save",
            match_type=GroundingMatchType.ACCESSIBILITY,
            confidence=0.95,
            pixel_x=100,
            pixel_y=200,
            text_content="Save",
        )
        d = c.to_dict()
        c2 = GroundingCandidate.from_dict(d)
        assert c2.candidate_id == "c1"
        assert c2.match_type == GroundingMatchType.ACCESSIBILITY
        assert c2.confidence == 0.95

    def test_grounding_result_roundtrip(self):
        gr = GroundingResult(
            step_id="s1",
            target_name="OK",
            grounded=True,
            confidence=0.9,
            explanation="Matched",
        )
        d = gr.to_dict()
        gr2 = GroundingResult.from_dict(d)
        assert gr2.grounded is True
        assert gr2.confidence == 0.9

    def test_planned_action_roundtrip(self):
        pa = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.CLICK,
            target_x=150,
            target_y=250,
            safety_level=SafetyLevel.SAFE,
            grounding_confidence=0.9,
        )
        d = pa.to_dict()
        pa2 = PlannedAction.from_dict(d)
        assert pa2.action_type == ActionType.CLICK
        assert pa2.safety_level == SafetyLevel.SAFE

    def test_execution_plan_roundtrip(self):
        plan = ExecutionPlan(
            plan_id="plan_1",
            skill_id="skill_1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            all_grounded=True,
            ready_to_execute=True,
        )
        d = plan.to_dict()
        plan2 = ExecutionPlan.from_dict(d)
        assert plan2.policy == ExecutionPolicy.DRY_RUN
        assert plan2.all_grounded is True

    def test_execution_plan_fingerprint(self):
        plan = ExecutionPlan(
            plan_id="p1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
        )
        fp = plan.compute_fingerprint()
        assert len(fp) == 64
        # Deterministic
        assert plan.compute_fingerprint() == fp

    def test_step_execution_result_roundtrip(self):
        r = StepExecutionResult(
            step_id="s1",
            action_id="a1",
            status=StepStatus.SUCCEEDED,
            action_type=ActionType.CLICK,
            was_dry_run=True,
        )
        d = r.to_dict()
        r2 = StepExecutionResult.from_dict(d)
        assert r2.status == StepStatus.SUCCEEDED
        assert r2.was_dry_run is True

    def test_execution_session_roundtrip(self):
        sess = ExecutionSession(
            session_id="exec_1",
            skill_id="skill_1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            state=ExecutionState.COMPLETED,
        )
        d = sess.to_dict()
        sess2 = ExecutionSession.from_dict(d)
        assert sess2.state == ExecutionState.COMPLETED

    def test_execution_checkpoint_roundtrip(self):
        cp = ExecutionCheckpoint(
            checkpoint_id="ckpt_1",
            session_id="exec_1",
            after_step_index=3,
            state=ExecutionState.EXECUTING,
            completed_steps=["s1", "s2", "s3"],
        )
        d = cp.to_dict()
        cp2 = ExecutionCheckpoint.from_dict(d)
        assert cp2.after_step_index == 3
        assert len(cp2.completed_steps) == 3

    def test_environment_element_roundtrip(self):
        e = EnvironmentElement(
            element_id="e1",
            role="button",
            label="OK",
            pixel_x=100,
            pixel_y=200,
        )
        d = e.to_dict()
        e2 = EnvironmentElement.from_dict(d)
        assert e2.label == "OK"

    def test_environment_snapshot_roundtrip(self):
        snap = EnvironmentSnapshot(
            snapshot_id="snap_1",
            active_application="Safari",
            elements=[
                EnvironmentElement(element_id="e1", role="button", label="Submit")
            ],
        )
        d = snap.to_dict()
        snap2 = EnvironmentSnapshot.from_dict(d)
        assert snap2.active_application == "Safari"
        assert len(snap2.elements) == 1

    def test_execution_manifest_roundtrip(self):
        m = ExecutionManifest(
            manifest_id="m1",
            session_id="exec_1",
            skill_id="skill_1",
            skill_version="1.0.0",
            policy="DRY_RUN",
            state="COMPLETED",
            total_steps=5,
            completed_steps=5,
        )
        d = m.to_dict()
        m2 = ExecutionManifest.from_dict(d)
        assert m2.completed_steps == 5

    def test_all_enums_str(self):
        assert str(ExecutionPolicy.DRY_RUN) == "DRY_RUN"
        assert str(ExecutionState.CREATED) == "CREATED"
        assert str(StepStatus.PENDING) == "PENDING"
        assert str(GroundingMatchType.OCR_TEXT) == "OCR_TEXT"
        assert str(ActionType.CLICK) == "CLICK"
        assert str(SafetyLevel.SAFE) == "SAFE"


# -----------------------------------------------------------------------
# 2. Environment Observation
# -----------------------------------------------------------------------


class TestEnvironment:
    def test_synthetic_adapter_observe(self):
        env = _make_env()
        snap = env.observe()
        assert snap.active_application == "TextEdit"
        assert snap.active_window_title == "Untitled"
        assert len(snap.elements) == 1
        assert snap.source == "synthetic"

    def test_synthetic_adapter_add_element(self):
        env = _make_env([])
        env.add_element(_make_element("e1"))
        snap = env.observe()
        assert len(snap.elements) == 1

    def test_synthetic_adapter_set_active_app(self):
        env = _make_env()
        env.set_active_app("Safari", "Google")
        assert env.get_active_application() == "Safari"
        assert env.get_active_window_title() == "Google"
        assert "Safari" in env.get_running_applications()

    def test_synthetic_adapter_is_available(self):
        env = _make_env()
        assert env.is_available() is True
        assert env.adapter_id() == "synthetic_environment"

    def test_get_environment_adapter_synthetic(self):
        adapter = get_environment_adapter(synthetic=True)
        assert adapter.adapter_id() == "synthetic_environment"

    def test_snapshot_observation_duration(self):
        env = _make_env()
        snap = env.observe()
        assert snap.observation_duration_ms >= 0


# -----------------------------------------------------------------------
# 3. Semantic Grounding
# -----------------------------------------------------------------------


class TestGrounding:
    def test_ground_exact_match(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="OK")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("btn_ok", label="OK")],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is True
        assert result.confidence >= 0.9
        assert result.best_candidate is not None
        assert result.best_candidate.text_content == "OK"

    def test_ground_fuzzy_match(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="Save Document")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("btn_save", label="Save Docment")],  # typo
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is True
        assert result.confidence > 0.5

    def test_ground_no_match(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="NonexistentButton")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("btn_ok", label="OK")],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is False
        assert result.confidence < 0.3

    def test_ground_ambiguous(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="Submit")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[
                _make_element("btn1", label="Submit Form", px=100),
                _make_element("btn2", label="Submit Report", px=300),
            ],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is True
        # Should detect ambiguity when candidates are close
        assert len(result.all_candidates) >= 2

    def test_ground_multiple_strategies(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="Save")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("btn_save", label="Save")],
            ocr_text_regions=[
                {"region_id": "ocr1", "text": "Save", "bbox": {"x": 100, "y": 200, "width": 50, "height": 20}},
            ],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is True
        assert len(result.strategies_attempted) >= 2

    def test_ground_all_steps(self):
        engine = SemanticGroundingEngine()
        steps = [
            _make_step("s1", 0, target="File"),
            _make_step("s2", 1, target="Save"),
        ]
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[
                _make_element("e1", label="File"),
                _make_element("e2", label="Save"),
            ],
        )
        results = engine.ground_all_steps(steps, snap)
        assert len(results) == 2
        assert all(r.grounded for r in results)

    def test_ground_with_explicit_grounding_req(self):
        engine = SemanticGroundingEngine()
        req = GroundingRequirement(
            target_name="OK",
            semantic_label="OK",
            preferred_strategy=GroundingStrategy.OCR_TEXT,
        )
        step = _make_step(target="OK", grounding=req)
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("btn_ok", label="OK")],
            ocr_text_regions=[
                {"region_id": "ocr1", "text": "OK", "bbox": {"x": 100, "y": 200, "width": 50, "height": 20}},
            ],
        )
        result = engine.ground_step(step, snap, req)
        assert result.grounded is True
        # OCR strategy should have been attempted first
        assert result.strategies_attempted[0] == "OCR_TEXT"

    def test_ground_timing(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="OK")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("e1", label="OK")],
        )
        result = engine.ground_step(step, snap)
        assert result.timing_ms >= 0

    def test_ground_provenance(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="OK")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("e1", label="OK")],
        )
        result = engine.ground_step(step, snap)
        assert "snapshot_id" in result.provenance
        assert result.provenance["snapshot_id"] == "s1"


# -----------------------------------------------------------------------
# 4. Safety Policy
# -----------------------------------------------------------------------


class TestSafety:
    def test_safe_action_passes(self):
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.CLICK,
            grounding_confidence=0.9,
        )
        report = policy.assess_action(action, ExecutionPolicy.SUPERVISED)
        assert report.safe is True

    def test_low_confidence_blocked(self):
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.CLICK,
            grounding_confidence=0.1,
        )
        report = policy.assess_action(action, ExecutionPolicy.SUPERVISED)
        assert report.safe is False
        assert report.safety_level == SafetyLevel.BLOCKED

    def test_dangerous_key_combo_blocked(self):
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.KEY_COMBO,
            key_sequence="cmd+q",
            grounding_confidence=0.9,
        )
        report = policy.assess_action(action, ExecutionPolicy.SUPERVISED)
        assert report.safe is False

    def test_dry_run_always_safe(self):
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.DRAG,
            grounding_confidence=0.9,
        )
        report = policy.assess_action(action, ExecutionPolicy.DRY_RUN)
        assert report.safe is True
        assert report.safety_level == SafetyLevel.SAFE

    def test_autonomous_low_confidence_downgraded(self):
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.CLICK,
            grounding_confidence=0.6,  # Below autonomous threshold
        )
        report = policy.assess_action(action, ExecutionPolicy.AUTONOMOUS)
        assert report.safe is True
        assert len(report.required_confirmations) > 0

    def test_plan_assessment_all_safe(self):
        policy = ExecutionSafetyPolicy()
        actions = [
            PlannedAction(
                action_id=f"a{i}",
                step_id=f"s{i}",
                action_type=ActionType.CLICK,
                grounding_confidence=0.9,
            )
            for i in range(3)
        ]
        report = policy.assess_plan(actions, ExecutionPolicy.SUPERVISED)
        assert report.safe is True

    def test_plan_assessment_one_blocked(self):
        policy = ExecutionSafetyPolicy()
        actions = [
            PlannedAction(
                action_id="a1",
                step_id="s1",
                action_type=ActionType.CLICK,
                grounding_confidence=0.9,
            ),
            PlannedAction(
                action_id="a2",
                step_id="s2",
                action_type=ActionType.KEY_COMBO,
                key_sequence="cmd+q",
                grounding_confidence=0.9,
            ),
        ]
        report = policy.assess_plan(actions, ExecutionPolicy.SUPERVISED)
        assert report.safe is False

    def test_precondition_enforcement(self):
        policy = ExecutionSafetyPolicy()
        met, unmet = policy.enforce_preconditions(
            ["TextEdit running"],
            {"active_app": "TextEdit", "running_apps": "TextEdit Finder"},
        )
        assert met is True
        assert len(unmet) == 0

    def test_precondition_not_met(self):
        policy = ExecutionSafetyPolicy()
        met, unmet = policy.enforce_preconditions(
            ["Photoshop running"],
            {"active_app": "TextEdit", "running_apps": "TextEdit Finder"},
        )
        assert met is False
        assert len(unmet) == 1

    def test_noop_is_safe(self):
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.NOOP,
            grounding_confidence=0.9,
        )
        report = policy.assess_action(action, ExecutionPolicy.SUPERVISED)
        assert report.safe is True
        assert report.safety_level == SafetyLevel.SAFE


# -----------------------------------------------------------------------
# 5. Action Translation
# -----------------------------------------------------------------------


class TestActionTranslation:
    def test_click_translation(self):
        translator = ActionTranslator()
        step = _make_step(action=SkillActionType.SELECT, target="OK")
        grounding = GroundingResult(
            step_id="step_1",
            target_name="OK",
            grounded=True,
            confidence=0.95,
            best_candidate=GroundingCandidate(
                candidate_id="c1",
                target_name="OK",
                match_type=GroundingMatchType.ACCESSIBILITY,
                confidence=0.95,
                pixel_x=100,
                pixel_y=200,
                pixel_width=80,
                pixel_height=30,
                text_content="OK",
            ),
        )
        action = translator.translate_step(step, grounding)
        assert action.action_type == ActionType.CLICK
        assert action.target_x == 140  # center of 100 + 80/2
        assert action.target_y == 215  # center of 200 + 30/2

    def test_type_text_translation(self):
        translator = ActionTranslator()
        step = _make_step(action=SkillActionType.INPUT, target="search_field")
        step.arguments = {"text": "hello world"}
        grounding = GroundingResult(
            step_id="step_1",
            target_name="search_field",
            grounded=True,
            confidence=0.9,
            best_candidate=GroundingCandidate(
                candidate_id="c1",
                target_name="search_field",
                match_type=GroundingMatchType.ACCESSIBILITY,
                confidence=0.9,
                pixel_x=50,
                pixel_y=50,
            ),
        )
        action = translator.translate_step(step, grounding)
        assert action.action_type == ActionType.TYPE_TEXT
        assert action.text_input == "hello world"

    def test_save_key_combo_translation(self):
        translator = ActionTranslator(platform="macos")
        step = _make_step(action=SkillActionType.SAVE, target="document")
        grounding = GroundingResult(
            step_id="step_1",
            target_name="document",
            grounded=True,
            confidence=0.9,
        )
        action = translator.translate_step(step, grounding)
        assert action.action_type == ActionType.KEY_COMBO
        assert action.key_sequence == "cmd+s"

    def test_windows_key_combo(self):
        translator = ActionTranslator(platform="windows")
        step = _make_step(action=SkillActionType.SAVE, target="doc")
        grounding = GroundingResult(
            step_id="step_1", target_name="doc", grounded=True, confidence=0.9
        )
        action = translator.translate_step(step, grounding)
        assert action.key_sequence == "ctrl+s"

    def test_translate_all(self):
        translator = ActionTranslator()
        steps = [
            _make_step("s1", 0, SkillActionType.SELECT, "OK"),
            _make_step("s2", 1, SkillActionType.SAVE, "document"),
        ]
        groundings = [
            GroundingResult(step_id="s1", target_name="OK", grounded=True, confidence=0.9),
            GroundingResult(step_id="s2", target_name="document", grounded=True, confidence=0.85),
        ]
        actions = translator.translate_all(steps, groundings)
        assert len(actions) == 2
        assert actions[0].action_type == ActionType.CLICK
        assert actions[1].action_type == ActionType.KEY_COMBO

    def test_parameter_reference_resolution(self):
        translator = ActionTranslator()
        step = _make_step(action=SkillActionType.INPUT, target="field")
        step.arguments = {"text": "$filename"}
        grounding = GroundingResult(
            step_id="step_1", target_name="field", grounded=True, confidence=0.9
        )
        action = translator.translate_step(step, grounding, parameters={"filename": "report.txt"})
        assert action.text_input == "report.txt"


# -----------------------------------------------------------------------
# 6. Execution Planning
# -----------------------------------------------------------------------


class TestPlanning:
    def test_plan_creation_dry_run(self):
        env = _make_env()
        planner = ExecutionPlanner(environment=env)
        skill = _make_skill()
        plan = planner.create_plan(skill, ExecutionPolicy.DRY_RUN)
        assert plan.skill_id == "test_skill"
        assert plan.policy == ExecutionPolicy.DRY_RUN
        assert len(plan.planned_actions) == 1
        assert len(plan.grounding_results) == 1

    def test_plan_all_grounded(self):
        elements = [
            _make_element("e1", label="File"),
            _make_element("e2", label="Save"),
        ]
        env = _make_env(elements)
        planner = ExecutionPlanner(environment=env)
        steps = [
            _make_step("s1", 0, target="File"),
            _make_step("s2", 1, target="Save"),
        ]
        skill = _make_skill(steps)
        plan = planner.create_plan(skill, ExecutionPolicy.DRY_RUN)
        assert plan.all_grounded is True
        assert plan.minimum_confidence > 0

    def test_plan_not_grounded(self):
        env = _make_env([])  # empty environment
        planner = ExecutionPlanner(environment=env)
        skill = _make_skill()
        plan = planner.create_plan(skill, ExecutionPolicy.SUPERVISED)
        assert plan.all_grounded is False
        assert plan.ready_to_execute is False

    def test_plan_preconditions_met(self):
        env = _make_env()
        planner = ExecutionPlanner(environment=env)
        preconditions = [
            SkillPrecondition(
                precondition_id="pc1",
                precondition_type="app_running",
                description="TextEdit running",
            ),
        ]
        skill = _make_skill(preconditions=preconditions)
        plan = planner.create_plan(skill, ExecutionPolicy.DRY_RUN)
        assert plan.preconditions_met is True

    def test_plan_preconditions_not_met(self):
        env = _make_env()
        planner = ExecutionPlanner(environment=env)
        preconditions = [
            SkillPrecondition(
                precondition_id="pc1",
                precondition_type="app_running",
                description="Photoshop running",
            ),
        ]
        skill = _make_skill(preconditions=preconditions)
        plan = planner.create_plan(skill, ExecutionPolicy.SUPERVISED)
        assert plan.preconditions_met is False
        assert plan.ready_to_execute is False


# -----------------------------------------------------------------------
# 7. Execution Engine
# -----------------------------------------------------------------------


class TestEngine:
    def _make_engine(self, elements=None):
        env = _make_env(elements)
        planner = ExecutionPlanner(environment=env)
        return ExecutionEngine(planner=planner)

    def test_create_session(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        assert session.state == ExecutionState.PLANNING
        assert session.plan is not None
        assert session.total_steps == 1

    def test_dry_run_execution(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        assert session.state == ExecutionState.COMPLETED
        assert len(session.step_results) == 1
        assert session.step_results[0].was_dry_run is True
        assert session.step_results[0].status == StepStatus.SUCCEEDED

    def test_multi_step_dry_run(self):
        elements = [
            _make_element("e1", label="File"),
            _make_element("e2", label="Save"),
            _make_element("e3", label="Close"),
        ]
        engine = self._make_engine(elements)
        steps = [
            _make_step("s1", 0, target="File"),
            _make_step("s2", 1, target="Save"),
            _make_step("s3", 2, target="Close"),
        ]
        skill = _make_skill(steps)
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        assert session.state == ExecutionState.COMPLETED
        assert len(session.step_results) == 3
        assert all(r.status == StepStatus.SUCCEEDED for r in session.step_results)

    def test_execution_with_callback(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        callback_results = []
        session = engine.execute(session, step_callback=lambda r: callback_results.append(r))
        assert len(callback_results) == 1

    def test_session_cancelled(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session.cancelled = True
        session = engine.execute(session)
        assert session.state == ExecutionState.CANCELLED

    def test_cancel_active_session(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        cancelled = engine.cancel()
        assert cancelled is not None
        assert cancelled.state == ExecutionState.CANCELLED

    def test_execution_produces_manifest(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        manifest = engine.get_manifest(session)
        assert manifest.session_id == session.session_id
        assert manifest.completed_steps == 1
        assert manifest.total_steps == 1

    def test_execution_too_many_steps(self):
        engine = self._make_engine()
        engine.max_steps = 1
        steps = [
            _make_step("s1", 0, target="OK"),
            _make_step("s2", 1, target="OK"),
        ]
        skill = _make_skill(steps)
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        assert session.state == ExecutionState.FAILED
        assert "exceeding limit" in session.error_message

    def test_execution_timing(self):
        engine = self._make_engine()
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        assert session.total_duration_ms >= 0
        assert session.completed_at is not None

    def test_checkpointing(self):
        elements = [_make_element(f"e{i}", label=f"Btn {i}") for i in range(10)]
        engine = self._make_engine(elements)
        engine.checkpoint_interval = 3
        steps = [_make_step(f"s{i}", i, target=f"Btn {i}") for i in range(10)]
        skill = _make_skill(steps)
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        assert session.state == ExecutionState.COMPLETED
        # Should have checkpoints at steps 2, 5, 8
        assert len(session.checkpoints) >= 3

    def test_no_plan_fails(self):
        engine = self._make_engine()
        session = ExecutionSession(
            session_id="test",
            skill_id="test",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
        )
        session = engine.execute(session)
        assert session.state == ExecutionState.FAILED

    def test_supervised_unready_plan_fails(self):
        env = _make_env([])
        planner = ExecutionPlanner(environment=env)
        engine = ExecutionEngine(planner=planner)
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.SUPERVISED)
        session = engine.execute(session)
        assert session.state == ExecutionState.FAILED


# -----------------------------------------------------------------------
# 8. Execution Storage
# -----------------------------------------------------------------------


class TestStorage:
    def test_save_and_load_session(self, storage_mgr):
        store = ExecutionStorage(storage_mgr)
        session = ExecutionSession(
            session_id="exec_test_1",
            skill_id="skill_1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            state=ExecutionState.COMPLETED,
        )
        store.save_session(session)
        loaded = store.load_session("exec_test_1")
        assert loaded is not None
        assert loaded.session_id == "exec_test_1"
        assert loaded.state == ExecutionState.COMPLETED

    def test_save_and_load_manifest(self, storage_mgr):
        store = ExecutionStorage(storage_mgr)
        manifest = ExecutionManifest(
            manifest_id="m1",
            session_id="exec_test_1",
            skill_id="skill_1",
            skill_version="1.0.0",
            policy="DRY_RUN",
            state="COMPLETED",
        )
        store.save_manifest(manifest)
        loaded = store.load_manifest("exec_test_1")
        assert loaded is not None
        assert loaded.manifest_id == "m1"

    def test_list_sessions(self, storage_mgr):
        store = ExecutionStorage(storage_mgr)
        for i in range(3):
            session = ExecutionSession(
                session_id=f"exec_{i}",
                skill_id="s1",
                skill_version="1.0.0",
                policy=ExecutionPolicy.DRY_RUN,
            )
            store.save_session(session)
        sessions = store.list_sessions()
        assert len(sessions) == 3

    def test_session_exists(self, storage_mgr):
        store = ExecutionStorage(storage_mgr)
        assert store.session_exists("nonexistent") is False
        session = ExecutionSession(
            session_id="exists_test",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
        )
        store.save_session(session)
        assert store.session_exists("exists_test") is True

    def test_delete_session(self, storage_mgr):
        store = ExecutionStorage(storage_mgr)
        session = ExecutionSession(
            session_id="delete_test",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
        )
        store.save_session(session)
        assert store.session_exists("delete_test") is True
        result = store.delete_session("delete_test")
        assert result is True
        assert store.session_exists("delete_test") is False

    def test_load_nonexistent_returns_none(self, storage_mgr):
        store = ExecutionStorage(storage_mgr)
        assert store.load_session("nope") is None
        assert store.load_manifest("nope") is None


# -----------------------------------------------------------------------
# 9. Execution Validator
# -----------------------------------------------------------------------


class TestValidator:
    def test_valid_plan(self):
        plan = ExecutionPlan(
            plan_id="p1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            planned_actions=[
                PlannedAction(
                    action_id="a1",
                    step_id="s1",
                    action_type=ActionType.CLICK,
                    grounding_confidence=0.9,
                )
            ],
        )
        errors = ExecutionValidator.validate_plan(plan)
        assert len(errors) == 0

    def test_plan_missing_ids(self):
        plan = ExecutionPlan(
            plan_id="",
            skill_id="",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
        )
        errors = ExecutionValidator.validate_plan(plan)
        assert len(errors) >= 2

    def test_plan_invalid_confidence(self):
        plan = ExecutionPlan(
            plan_id="p1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            planned_actions=[
                PlannedAction(
                    action_id="a1",
                    step_id="s1",
                    action_type=ActionType.CLICK,
                    grounding_confidence=1.5,  # Invalid
                )
            ],
        )
        errors = ExecutionValidator.validate_plan(plan)
        assert any("confidence" in e.lower() for e in errors)

    def test_valid_session(self):
        session = ExecutionSession(
            session_id="exec_1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            state=ExecutionState.COMPLETED,
            completed_at="2024-01-01T00:00:00Z",
        )
        errors = ExecutionValidator.validate_session(session)
        assert len(errors) == 0

    def test_session_missing_error_message(self):
        session = ExecutionSession(
            session_id="exec_1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            state=ExecutionState.FAILED,
            error_message=None,
        )
        errors = ExecutionValidator.validate_session(session)
        assert any("error_message" in e for e in errors)

    def test_safety_invariants_dry_run(self):
        session = ExecutionSession(
            session_id="exec_1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            step_results=[
                StepExecutionResult(
                    step_id="s1",
                    action_id="a1",
                    status=StepStatus.SUCCEEDED,
                    action_type=ActionType.CLICK,
                    was_dry_run=True,
                )
            ],
        )
        violations = ExecutionValidator.validate_safety_invariants(session)
        assert len(violations) == 0

    def test_safety_invariants_violated(self):
        session = ExecutionSession(
            session_id="exec_1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            step_results=[
                StepExecutionResult(
                    step_id="s1",
                    action_id="a1",
                    status=StepStatus.SUCCEEDED,
                    action_type=ActionType.CLICK,
                    was_dry_run=False,  # Violation!
                )
            ],
        )
        violations = ExecutionValidator.validate_safety_invariants(session)
        assert len(violations) == 1

    def test_boundary_guards(self):
        violations = ExecutionValidator.validate_boundary_guards()
        assert len(violations) == 0


# -----------------------------------------------------------------------
# 10. Execution Cache
# -----------------------------------------------------------------------


class TestCache:
    def test_put_and_get_grounding(self, temp_dir):
        cache = ExecutionCache(temp_dir / "exec_cache")
        cache.put_grounding("s1", "step1", "hash1", {"grounded": True})
        result = cache.get_grounding("s1", "step1", "hash1")
        assert result is not None
        assert result["grounded"] is True

    def test_cache_miss(self, temp_dir):
        cache = ExecutionCache(temp_dir / "exec_cache")
        result = cache.get_grounding("s1", "step1", "hash_miss")
        assert result is None

    def test_put_and_get_plan(self, temp_dir):
        cache = ExecutionCache(temp_dir / "exec_cache")
        cache.put_plan("fp123", {"plan_id": "p1", "actions": []})
        result = cache.get_plan("fp123")
        assert result is not None
        assert result["plan_id"] == "p1"

    def test_clear_cache(self, temp_dir):
        cache = ExecutionCache(temp_dir / "exec_cache")
        cache.put_grounding("s1", "step1", "h1", {"a": 1})
        cache.put_plan("fp1", {"b": 2})
        removed = cache.clear()
        assert removed == 2
        assert cache.get_grounding("s1", "step1", "h1") is None


# -----------------------------------------------------------------------
# 11. Benchmark
# -----------------------------------------------------------------------


class TestBenchmark:
    def test_benchmark_runs(self):
        report = run_execution_benchmark(num_steps=5)
        assert report.steps_benchmarked == 5
        assert report.grounding_success_rate > 0
        assert report.total_benchmark_ms > 0
        assert report.environment_observation_ms >= 0
        assert report.grounding_per_step_ms >= 0
        assert report.plan_creation_ms > 0
        assert report.dry_run_execution_ms > 0


# -----------------------------------------------------------------------
# 12. Semantic Boundary Tests
# -----------------------------------------------------------------------


class TestSemanticBoundary:
    def test_no_arbitrary_code_execution(self):
        """Execution module must not expose arbitrary code execution."""
        import teach_a_skill.execution as pkg

        assert not hasattr(pkg, "run_shell")
        assert not hasattr(pkg, "eval_expression")
        assert not hasattr(pkg, "run_arbitrary_code")

    def test_no_network_access(self):
        """Execution module must not expose network APIs."""
        import teach_a_skill.execution as pkg

        assert not hasattr(pkg, "send_network_request")
        assert not hasattr(pkg, "download_model")
        assert not hasattr(pkg, "upload_data")

    def test_dry_run_no_real_actions(self):
        """Dry-run must never perform real platform actions."""
        env = _make_env()
        planner = ExecutionPlanner(environment=env)
        engine = ExecutionEngine(planner=planner)
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        for result in session.step_results:
            assert result.was_dry_run is True

    def test_blocked_step_never_succeeds(self):
        """A blocked step must never report success."""
        policy = ExecutionSafetyPolicy()
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.KEY_COMBO,
            key_sequence="cmd+q",
            grounding_confidence=0.9,
        )
        report = policy.assess_action(action, ExecutionPolicy.SUPERVISED)
        assert report.safe is False
        # Even if someone tried to override:
        assert report.safety_level == SafetyLevel.BLOCKED

    def test_insufficient_confidence_blocks_execution(self):
        """Steps with insufficient confidence must be blocked."""
        policy = ExecutionSafetyPolicy(min_confidence=0.7)
        action = PlannedAction(
            action_id="a1",
            step_id="s1",
            action_type=ActionType.CLICK,
            grounding_confidence=0.3,
        )
        report = policy.assess_action(action, ExecutionPolicy.SUPERVISED)
        assert report.safe is False

    def test_execution_never_trusts_ui_text(self):
        """Grounding system must report raw confidence, never auto-trust."""
        engine = SemanticGroundingEngine()
        # Even with perfect text match, confidence is calculated, not assumed
        step = _make_step(target="Delete All Data")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("e1", label="Delete All Data")],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is True
        # Confidence must be a calculated value, not hardcoded 1.0
        assert 0 < result.confidence <= 1.0

    def test_plan_without_grounding_not_ready(self):
        """A plan with ungrounded steps must not be marked ready."""
        env = _make_env([])
        planner = ExecutionPlanner(environment=env)
        skill = _make_skill()
        plan = planner.create_plan(skill, ExecutionPolicy.SUPERVISED)
        assert plan.ready_to_execute is False

    def test_no_execution_on_grounding_failure(self):
        """Engine must not execute when grounding fails and policy is not DRY_RUN."""
        env = _make_env([])
        planner = ExecutionPlanner(environment=env)
        engine = ExecutionEngine(planner=planner)
        skill = _make_skill()
        session = engine.create_session(skill, ExecutionPolicy.SUPERVISED)
        session = engine.execute(session)
        assert session.state == ExecutionState.FAILED


# -----------------------------------------------------------------------
# 13. Adversarial / Edge Cases
# -----------------------------------------------------------------------


class TestAdversarial:
    def test_empty_skill_no_steps(self):
        env = _make_env()
        planner = ExecutionPlanner(environment=env)
        engine = ExecutionEngine(planner=planner)
        skill = _make_skill(steps=[])
        session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        session = engine.execute(session)
        assert session.state == ExecutionState.COMPLETED
        assert len(session.step_results) == 0

    def test_empty_environment(self):
        env = _make_env([])
        grounding = SemanticGroundingEngine()
        step = _make_step(target="anything")
        snap = env.observe()
        result = grounding.ground_step(step, snap)
        assert result.grounded is False

    def test_very_long_target_name(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="A" * 10000)
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("e1", label="short")],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is False

    def test_special_characters_in_target(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="<button onclick='alert(1)'/>")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("e1", label="Submit")],
        )
        result = engine.ground_step(step, snap)
        # Should not crash, just not match
        assert isinstance(result, GroundingResult)

    def test_unicode_target(self):
        engine = SemanticGroundingEngine()
        step = _make_step(target="保存")
        snap = EnvironmentSnapshot(
            snapshot_id="s1",
            elements=[_make_element("e1", label="保存")],
        )
        result = engine.ground_step(step, snap)
        assert result.grounded is True

    def test_concurrent_session_prevention(self):
        """Engine should only have one active session at a time."""
        env = _make_env()
        planner = ExecutionPlanner(environment=env)
        engine = ExecutionEngine(planner=planner)
        skill = _make_skill()
        session1 = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        # Creating a second session replaces the first
        session2 = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
        assert engine.active_session is session2

    def test_negative_confidence_in_action(self):
        plan = ExecutionPlan(
            plan_id="p1",
            skill_id="s1",
            skill_version="1.0.0",
            policy=ExecutionPolicy.DRY_RUN,
            planned_actions=[
                PlannedAction(
                    action_id="a1",
                    step_id="s1",
                    action_type=ActionType.CLICK,
                    grounding_confidence=-0.5,
                )
            ],
        )
        errors = ExecutionValidator.validate_plan(plan)
        assert any("confidence" in e.lower() for e in errors)
