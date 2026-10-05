"""Safety policy and permission enforcement for execution.

The fundamental rule: execute only what can be grounded, authorized, and verified.
Never execute when confidence is insufficient.
Never trust UI text as an instruction.
Never execute arbitrary code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from teach_a_skill.execution.models import (
    ActionType,
    ExecutionPolicy,
    PlannedAction,
    SafetyLevel,
)

logger = logging.getLogger(__name__)

# Actions that are always safe (read-only, no state changes)
SAFE_ACTIONS = frozenset({
    ActionType.NOOP,
    ActionType.WAIT,
    ActionType.FOCUS,
})

# Actions that are moderately safe (state changes with easy reversal)
MODERATE_ACTIONS = frozenset({
    ActionType.CLICK,
    ActionType.DOUBLE_CLICK,
    ActionType.TYPE_TEXT,
    ActionType.KEY_PRESS,
    ActionType.KEY_COMBO,
    ActionType.SCROLL,
    ActionType.ACTIVATE_WINDOW,
    ActionType.ACTIVATE_APP,
})

# Actions with higher risk (harder to reverse)
HIGH_RISK_ACTIONS = frozenset({
    ActionType.DRAG,
    ActionType.RIGHT_CLICK,
})

# Actions that are always blocked (never allowed)
BLOCKED_ACTIONS: frozenset[ActionType] = frozenset()

# Dangerous key combinations that should be blocked or flagged
DANGEROUS_KEY_COMBOS = frozenset({
    "cmd+q",
    "cmd+shift+q",
    "alt+f4",
    "ctrl+alt+delete",
    "cmd+shift+delete",
    "ctrl+shift+delete",
})

# Minimum confidence required to execute (below → blocked)
MIN_EXECUTION_CONFIDENCE = 0.5

# Minimum confidence for autonomous execution (below → needs supervision)
MIN_AUTONOMOUS_CONFIDENCE = 0.8


@dataclass
class SafetyReport:
    """Assessment of execution safety for a single action or plan."""

    safe: bool
    safety_level: SafetyLevel
    blocked_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    required_confirmations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "safety_level": str(self.safety_level),
            "blocked_reason": self.blocked_reason,
            "warnings": self.warnings,
            "required_confirmations": self.required_confirmations,
            "metadata": self.metadata,
        }


class ExecutionSafetyPolicy:
    """Enforces execution safety constraints, permissions, and policy gates."""

    def __init__(
        self,
        min_confidence: float = MIN_EXECUTION_CONFIDENCE,
        min_autonomous_confidence: float = MIN_AUTONOMOUS_CONFIDENCE,
        allow_destructive_keys: bool = False,
    ) -> None:
        self.min_confidence = min_confidence
        self.min_autonomous_confidence = min_autonomous_confidence
        self.allow_destructive_keys = allow_destructive_keys

    def assess_action(
        self,
        action: PlannedAction,
        policy: ExecutionPolicy,
    ) -> SafetyReport:
        """Assess the safety of a single planned action.

        Args:
            action: The action to evaluate.
            policy: The current execution policy.

        Returns:
            A SafetyReport indicating whether the action is safe to proceed.
        """
        warnings: list[str] = []
        confirmations: list[str] = []

        # Check blocked actions
        if action.action_type in BLOCKED_ACTIONS:
            return SafetyReport(
                safe=False,
                safety_level=SafetyLevel.BLOCKED,
                blocked_reason=f"Action type '{action.action_type}' is unconditionally blocked.",
            )

        # Check dangerous key combos
        if action.action_type in (ActionType.KEY_COMBO, ActionType.KEY_PRESS):
            key_seq = (action.key_sequence or "").lower()
            if key_seq in DANGEROUS_KEY_COMBOS and not self.allow_destructive_keys:
                return SafetyReport(
                    safe=False,
                    safety_level=SafetyLevel.BLOCKED,
                    blocked_reason=f"Key combination '{action.key_sequence}' is blocked as potentially destructive.",
                )
            if key_seq in DANGEROUS_KEY_COMBOS:
                warnings.append(f"Dangerous key combination: {action.key_sequence}")

        # Check confidence
        if action.grounding_confidence < self.min_confidence:
            return SafetyReport(
                safe=False,
                safety_level=SafetyLevel.BLOCKED,
                blocked_reason=(
                    f"Grounding confidence {action.grounding_confidence:.2f} is below "
                    f"minimum threshold {self.min_confidence:.2f}"
                ),
            )

        # Determine safety level
        if action.action_type in SAFE_ACTIONS:
            safety = SafetyLevel.SAFE
        elif action.action_type in MODERATE_ACTIONS:
            safety = SafetyLevel.MODERATE
        elif action.action_type in HIGH_RISK_ACTIONS:
            safety = SafetyLevel.HIGH_RISK
            warnings.append(f"High-risk action: {action.action_type}")
        else:
            safety = SafetyLevel.MODERATE

        # Policy enforcement
        if policy == ExecutionPolicy.DRY_RUN:
            # All actions are safe in dry-run — they won't actually execute
            return SafetyReport(
                safe=True,
                safety_level=SafetyLevel.SAFE,
                warnings=["DRY RUN mode — no real actions will be performed"],
                metadata={"policy": "DRY_RUN", "original_safety": str(safety)},
            )

        if policy == ExecutionPolicy.AUTONOMOUS:
            if action.grounding_confidence < self.min_autonomous_confidence:
                confirmations.append(
                    f"Confidence {action.grounding_confidence:.2f} below autonomous threshold "
                    f"{self.min_autonomous_confidence:.2f} — would need supervision"
                )
                # Downgrade to supervised
                return SafetyReport(
                    safe=True,
                    safety_level=SafetyLevel.MODERATE,
                    warnings=warnings,
                    required_confirmations=confirmations,
                    metadata={"downgraded_from": "AUTONOMOUS", "policy": "SUPERVISED"},
                )

        return SafetyReport(
            safe=True,
            safety_level=safety,
            warnings=warnings,
            required_confirmations=confirmations,
            metadata={"policy": str(policy)},
        )

    def assess_plan(
        self,
        actions: list[PlannedAction],
        policy: ExecutionPolicy,
    ) -> SafetyReport:
        """Assess safety of the entire execution plan.

        Returns BLOCKED if any action is blocked.
        Returns the highest risk level among all actions.
        """
        overall_safe = True
        overall_level = SafetyLevel.SAFE
        all_warnings: list[str] = []
        all_confirmations: list[str] = []
        blocked_reason: Optional[str] = None

        safety_order = [SafetyLevel.SAFE, SafetyLevel.MODERATE, SafetyLevel.HIGH_RISK, SafetyLevel.BLOCKED]

        for action in actions:
            report = self.assess_action(action, policy)
            if not report.safe:
                overall_safe = False
                blocked_reason = report.blocked_reason
                overall_level = SafetyLevel.BLOCKED
                break
            all_warnings.extend(report.warnings)
            all_confirmations.extend(report.required_confirmations)
            if safety_order.index(report.safety_level) > safety_order.index(overall_level):
                overall_level = report.safety_level

        return SafetyReport(
            safe=overall_safe,
            safety_level=overall_level,
            blocked_reason=blocked_reason,
            warnings=all_warnings,
            required_confirmations=all_confirmations,
            metadata={"total_actions": len(actions), "policy": str(policy)},
        )

    def enforce_preconditions(
        self,
        precondition_descriptions: list[str],
        environment_state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Check whether skill preconditions are met.

        This is a semantic check — each precondition description is matched
        against environment state keys. Production systems would use NLU;
        this implementation uses keyword overlap as a baseline.

        Returns:
            Tuple of (all_met, list of unmet precondition descriptions).
        """
        unmet: list[str] = []
        state_text = " ".join(str(v) for v in environment_state.values()).lower()

        for desc in precondition_descriptions:
            # Simple keyword check for deterministic testing
            keywords = set(desc.lower().split())
            found = any(kw in state_text for kw in keywords)
            if not found:
                unmet.append(desc)

        return len(unmet) == 0, unmet


SafetyEnforcer = ExecutionSafetyPolicy

