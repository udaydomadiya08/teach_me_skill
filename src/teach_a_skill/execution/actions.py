"""Action abstraction layer: translates Skill IR steps into platform actions.

Maps semantic SkillActionType values to concrete ActionType platform actions,
resolves parameters, and builds PlannedAction sequences.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from teach_a_skill.execution.models import (
    ActionType,
    GroundingCandidate,
    GroundingResult,
    PlannedAction,
    SafetyLevel,
)
from teach_a_skill.skill.models import SkillActionType, SkillStep

logger = logging.getLogger(__name__)

# Mapping from semantic action types to platform action types
SEMANTIC_TO_PLATFORM: dict[SkillActionType, ActionType] = {
    SkillActionType.OPEN: ActionType.ACTIVATE_APP,
    SkillActionType.CLOSE: ActionType.KEY_COMBO,
    SkillActionType.SELECT: ActionType.CLICK,
    SkillActionType.INPUT: ActionType.TYPE_TEXT,
    SkillActionType.EDIT: ActionType.TYPE_TEXT,
    SkillActionType.NAVIGATE: ActionType.CLICK,
    SkillActionType.ACTIVATE: ActionType.CLICK,
    SkillActionType.SAVE: ActionType.KEY_COMBO,
    SkillActionType.CREATE: ActionType.KEY_COMBO,
    SkillActionType.DELETE: ActionType.KEY_COMBO,
    SkillActionType.MOVE: ActionType.DRAG,
    SkillActionType.RENAME: ActionType.TYPE_TEXT,
    SkillActionType.COPY: ActionType.KEY_COMBO,
    SkillActionType.PASTE: ActionType.KEY_COMBO,
    SkillActionType.SUBMIT: ActionType.CLICK,
    SkillActionType.WAIT_FOR_STATE: ActionType.WAIT,
    SkillActionType.VERIFY_STATE: ActionType.NOOP,
}

# Default key combos for known semantic actions
DEFAULT_KEY_COMBOS: dict[SkillActionType, str] = {
    SkillActionType.CLOSE: "cmd+w",
    SkillActionType.SAVE: "cmd+s",
    SkillActionType.CREATE: "cmd+n",
    SkillActionType.DELETE: "backspace",
    SkillActionType.COPY: "cmd+c",
    SkillActionType.PASTE: "cmd+v",
}


class ActionTranslator:
    """Translates semantic Skill IR steps into concrete platform PlannedActions."""

    def __init__(self, platform: str = "macos") -> None:
        self.platform = platform
        # Adjust key combos for platform
        if platform == "windows":
            self._key_combos = {
                SkillActionType.CLOSE: "ctrl+w",
                SkillActionType.SAVE: "ctrl+s",
                SkillActionType.CREATE: "ctrl+n",
                SkillActionType.DELETE: "delete",
                SkillActionType.COPY: "ctrl+c",
                SkillActionType.PASTE: "ctrl+v",
            }
        elif platform == "linux":
            self._key_combos = {
                SkillActionType.CLOSE: "ctrl+w",
                SkillActionType.SAVE: "ctrl+s",
                SkillActionType.CREATE: "ctrl+n",
                SkillActionType.DELETE: "delete",
                SkillActionType.COPY: "ctrl+c",
                SkillActionType.PASTE: "ctrl+v",
            }
        else:
            self._key_combos = dict(DEFAULT_KEY_COMBOS)

    def translate_step(
        self,
        step: SkillStep,
        grounding: GroundingResult,
        parameters: Optional[dict[str, Any]] = None,
    ) -> PlannedAction:
        """Translate a single Skill IR step into a PlannedAction.

        Args:
            step: The semantic skill step.
            grounding: The grounding result for this step's target.
            parameters: Resolved parameter values.

        Returns:
            A PlannedAction ready for execution or dry-run evaluation.
        """
        params = parameters or {}
        action_type = SEMANTIC_TO_PLATFORM.get(step.action_type, ActionType.NOOP)
        candidate = grounding.best_candidate

        # Determine target coordinates
        target_x = candidate.pixel_x + candidate.pixel_width / 2 if candidate else 0.0
        target_y = candidate.pixel_y + candidate.pixel_height / 2 if candidate else 0.0

        # Text input
        text_input: Optional[str] = None
        if action_type == ActionType.TYPE_TEXT:
            text_input = self._resolve_text_input(step, params)

        # Key sequence
        key_sequence: Optional[str] = None
        if action_type == ActionType.KEY_COMBO:
            key_sequence = self._resolve_key_sequence(step)

        # Safety classification
        safety = self._classify_safety(action_type, key_sequence)

        # Description
        desc = self._build_description(step, action_type, candidate, text_input, key_sequence)

        return PlannedAction(
            action_id=f"act_{step.step_id}_{uuid.uuid4().hex[:6]}",
            step_id=step.step_id,
            action_type=action_type,
            target_x=target_x,
            target_y=target_y,
            text_input=text_input,
            key_sequence=key_sequence,
            duration_ms=self._estimate_duration(action_type, text_input),
            safety_level=safety,
            description=desc,
            grounding_confidence=grounding.confidence,
            parameters=dict(step.arguments),
        )

    def translate_all(
        self,
        steps: list[SkillStep],
        groundings: list[GroundingResult],
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[PlannedAction]:
        """Translate all steps into planned actions."""
        grounding_map = {g.step_id: g for g in groundings}
        actions: list[PlannedAction] = []
        for step in steps:
            grounding = grounding_map.get(step.step_id)
            if not grounding:
                # Create an empty grounding result for ungrounded steps
                grounding = GroundingResult(
                    step_id=step.step_id,
                    target_name=step.target,
                    grounded=False,
                    confidence=0.0,
                    explanation="No grounding available",
                )
            actions.append(self.translate_step(step, grounding, parameters))
        return actions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_text_input(
        self, step: SkillStep, params: dict[str, Any]
    ) -> Optional[str]:
        """Resolve text to type from step arguments and parameters."""
        # Check step arguments first
        for key in ("text", "value", "input", "content"):
            if key in step.arguments:
                val = step.arguments[key]
                # Check if value is a parameter reference
                if isinstance(val, str) and val.startswith("$"):
                    param_name = val[1:]
                    return str(params.get(param_name, val))
                return str(val)
        # Check parameters
        for key in ("text", "value", "input"):
            if key in params:
                return str(params[key])
        return None

    def _resolve_key_sequence(self, step: SkillStep) -> Optional[str]:
        """Resolve the key sequence for key-based actions."""
        # Check step arguments for explicit key sequence
        for key in ("key_sequence", "shortcut", "keys"):
            if key in step.arguments:
                return str(step.arguments[key])
        # Fall back to default for this action type
        return self._key_combos.get(step.action_type)

    def _classify_safety(
        self, action_type: ActionType, key_sequence: Optional[str]
    ) -> SafetyLevel:
        """Classify the safety level of an action."""
        if action_type in (ActionType.NOOP, ActionType.WAIT, ActionType.FOCUS):
            return SafetyLevel.SAFE
        if action_type == ActionType.DRAG:
            return SafetyLevel.HIGH_RISK
        if key_sequence and key_sequence.lower() in {"cmd+q", "alt+f4", "ctrl+alt+delete"}:
            return SafetyLevel.BLOCKED
        if action_type in (ActionType.KEY_COMBO, ActionType.KEY_PRESS):
            return SafetyLevel.MODERATE
        return SafetyLevel.MODERATE

    def _estimate_duration(
        self, action_type: ActionType, text_input: Optional[str]
    ) -> float:
        """Estimate action duration in milliseconds."""
        base_durations: dict[ActionType, float] = {
            ActionType.CLICK: 50,
            ActionType.DOUBLE_CLICK: 100,
            ActionType.RIGHT_CLICK: 50,
            ActionType.TYPE_TEXT: 200,
            ActionType.KEY_PRESS: 30,
            ActionType.KEY_COMBO: 50,
            ActionType.SCROLL: 100,
            ActionType.DRAG: 300,
            ActionType.FOCUS: 30,
            ActionType.WAIT: 1000,
            ActionType.ACTIVATE_WINDOW: 200,
            ActionType.ACTIVATE_APP: 500,
            ActionType.NOOP: 0,
        }
        duration = base_durations.get(action_type, 100)
        if action_type == ActionType.TYPE_TEXT and text_input:
            duration += len(text_input) * 20  # ~20ms per character
        return duration

    def _build_description(
        self,
        step: SkillStep,
        action_type: ActionType,
        candidate: Optional[GroundingCandidate],
        text_input: Optional[str],
        key_sequence: Optional[str],
    ) -> str:
        """Build a human-readable description of the planned action."""
        target = candidate.text_content or candidate.target_name if candidate else step.target
        parts = [f"{action_type.value} on '{target}'"]

        if text_input:
            display_text = text_input[:50] + ("..." if len(text_input) > 50 else "")
            parts.append(f"text='{display_text}'")
        if key_sequence:
            parts.append(f"keys='{key_sequence}'")
        if candidate:
            parts.append(f"at ({candidate.pixel_x:.0f}, {candidate.pixel_y:.0f})")
            parts.append(f"confidence={candidate.confidence:.2f}")

        return " | ".join(parts)
