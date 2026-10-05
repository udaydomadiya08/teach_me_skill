"""Canonical failure, verification, and recovery data models for Phase 11.

Defines the failure taxonomy, severity levels, recoverability classifications,
idempotency models, recovery policies, recovery budgets, and verification results.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentElement,
    EnvironmentSnapshot,
    ExecutionCheckpoint,
    ExecutionPolicy,
    PlannedAction,
    SafetyLevel,
)

UIElementObservation = EnvironmentElement


@dataclass
class BoundingBox:
    """Rectangular pixel bounding box."""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundingBox":
        return cls(**data)



class FailureType(str, Enum):
    """Canonical failure taxonomy for Phase 11."""

    TRANSIENT_UI_CHANGE = "TRANSIENT_UI_CHANGE"
    TARGET_MOVED = "TARGET_MOVED"
    TARGET_DISAPPEARED = "TARGET_DISAPPEARED"
    TARGET_RENAMED = "TARGET_RENAMED"
    WINDOW_CHANGED = "WINDOW_CHANGED"
    APPLICATION_CHANGED = "APPLICATION_CHANGED"
    FOCUS_LOST = "FOCUS_LOST"
    TEMPORARY_DISABLED_STATE = "TEMPORARY_DISABLED_STATE"
    TEMPORARY_LOADING = "TEMPORARY_LOADING"
    TIMEOUT = "TIMEOUT"
    GROUNDING_FAILURE = "GROUNDING_FAILURE"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    PRECONDITION_FAILURE = "PRECONDITION_FAILURE"
    ACTION_FAILURE = "ACTION_FAILURE"
    POSTCONDITION_FAILURE = "POSTCONDITION_FAILURE"
    ENVIRONMENT_CHANGED = "ENVIRONMENT_CHANGED"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    POLICY_DENIED = "POLICY_DENIED"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    INVALID_SKILL = "INVALID_SKILL"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    RECOVERY_FAILURE = "RECOVERY_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"
    CANCELLED = "CANCELLED"

    def __str__(self) -> str:
        return self.value


class FailureSeverity(str, Enum):
    """Severity classification for execution failures."""

    INFO = "INFO"
    WARNING = "WARNING"
    RECOVERABLE = "RECOVERABLE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    def __str__(self) -> str:
        return self.value


class Recoverability(str, Enum):
    """Recoverability classification for execution failures."""

    AUTOMATICALLY_RECOVERABLE = "AUTOMATICALLY_RECOVERABLE"
    SUPERVISED_RECOVERABLE = "SUPERVISED_RECOVERABLE"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"
    NON_RECOVERABLE = "NON_RECOVERABLE"

    def __str__(self) -> str:
        return self.value


class ActionIdempotency(str, Enum):
    """Idempotency classification of platform actions."""

    IDEMPOTENT = "IDEMPOTENT"
    CONDITIONALLY_IDEMPOTENT = "CONDITIONALLY_IDEMPOTENT"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


class RecoveryStrategy(str, Enum):
    """Discrete, finite recovery strategies."""

    REOBSERVE = "REOBSERVE"
    REGROUND = "REGROUND"
    REFOCUS = "REFOCUS"
    WAIT_FOR_STATE = "WAIT_FOR_STATE"
    RETRY_IDEMPOTENT = "RETRY_IDEMPOTENT"
    RESTORE_CHECKPOINT = "RESTORE_CHECKPOINT"
    SAFE_ROLLBACK = "SAFE_ROLLBACK"
    ESCALATE = "ESCALATE"
    STOP = "STOP"

    def __str__(self) -> str:
        return self.value


class ExecutionOutcome(str, Enum):
    """Canonical execution outcomes."""

    SUCCESS = "SUCCESS"
    SUCCESS_AFTER_RECOVERY = "SUCCESS_AFTER_RECOVERY"
    FAILED_RECOVERABLE_EXHAUSTED = "FAILED_RECOVERABLE_EXHAUSTED"
    FAILED_UNRECOVERABLE = "FAILED_UNRECOVERABLE"
    FAILED_SECURITY = "FAILED_SECURITY"
    FAILED_POLICY = "FAILED_POLICY"
    FAILED_PRECONDITION = "FAILED_PRECONDITION"
    FAILED_POSTCONDITION = "FAILED_POSTCONDITION"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    USER_ABORTED = "USER_ABORTED"

    def __str__(self) -> str:
        return self.value


def compute_failure_fingerprint(
    skill_version: str,
    step_id: str,
    failure_type: FailureType,
    environment_signature: str,
    grounding_signature: str,
) -> str:
    """Compute a deterministic, invariant failure fingerprint excluding volatile timestamps."""
    payload = {
        "skill_version": skill_version,
        "step_id": step_id,
        "failure_type": str(failure_type),
        "environment_signature": environment_signature,
        "grounding_signature": grounding_signature,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class FailureRecord:
    """Immutable audit record of an execution failure."""

    failure_id: str
    execution_id: str
    step_id: str
    failure_type: FailureType
    severity: FailureSeverity
    recoverability: Recoverability
    confidence: float
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    failure_fingerprint: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "failure_type": str(self.failure_type),
            "severity": str(self.severity),
            "recoverability": str(self.recoverability),
            "confidence": round(self.confidence, 4),
            "explanation": self.explanation,
            "evidence": self.evidence,
            "failure_fingerprint": self.failure_fingerprint,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureRecord":
        d = dict(data)
        d["failure_type"] = FailureType(d["failure_type"])
        d["severity"] = FailureSeverity(d["severity"])
        d["recoverability"] = Recoverability(d["recoverability"])
        return cls(**d)


@dataclass
class VerificationResult:
    """Evidence-backed result of state verification."""

    verified: bool
    confidence: float
    evidence: dict[str, Any]
    source: str
    details: dict[str, Any] = field(default_factory=dict)
    conflict_detected: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "source": self.source,
            "details": self.details,
            "conflict_detected": self.conflict_detected,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        return cls(**data)


@dataclass
class RecoveryPolicy:
    """Enforces conservative constraints on recovery procedures."""

    max_retries_per_step: int = 3
    max_total_recovery_attempts: int = 10
    max_recovery_duration_s: float = 30.0
    allowed_recovery_types: list[FailureType] = field(
        default_factory=lambda: [
            FailureType.TRANSIENT_UI_CHANGE,
            FailureType.TARGET_MOVED,
            FailureType.TARGET_RENAMED,
            FailureType.FOCUS_LOST,
            FailureType.TEMPORARY_LOADING,
            FailureType.TEMPORARY_DISABLED_STATE,
            FailureType.TIMEOUT,
            FailureType.GROUNDING_FAILURE,
        ]
    )
    minimum_recovery_confidence: float = 0.6
    maximum_recovery_risk: SafetyLevel = SafetyLevel.MODERATE
    require_confirmation_for: list[RecoveryStrategy] = field(
        default_factory=lambda: [
            RecoveryStrategy.SAFE_ROLLBACK,
            RecoveryStrategy.RESTORE_CHECKPOINT,
            RecoveryStrategy.ESCALATE,
        ]
    )
    allow_regrounding: bool = True
    allow_checkpoint_restore: bool = True
    allow_safe_rollback: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries_per_step": self.max_retries_per_step,
            "max_total_recovery_attempts": self.max_total_recovery_attempts,
            "max_recovery_duration_s": self.max_recovery_duration_s,
            "allowed_recovery_types": [str(t) for t in self.allowed_recovery_types],
            "minimum_recovery_confidence": round(self.minimum_recovery_confidence, 4),
            "maximum_recovery_risk": str(self.maximum_recovery_risk),
            "require_confirmation_for": [str(s) for s in self.require_confirmation_for],
            "allow_regrounding": self.allow_regrounding,
            "allow_checkpoint_restore": self.allow_checkpoint_restore,
            "allow_safe_rollback": self.allow_safe_rollback,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryPolicy":
        d = dict(data)
        d["allowed_recovery_types"] = [FailureType(t) for t in d.get("allowed_recovery_types", [])]
        d["maximum_recovery_risk"] = SafetyLevel(d.get("maximum_recovery_risk", "MODERATE"))
        d["require_confirmation_for"] = [RecoveryStrategy(s) for s in d.get("require_confirmation_for", [])]
        return cls(**d)


@dataclass
class RecoveryBudget:
    """Finite budget tracking to prevent recovery loops and resource exhaustion."""

    step_retry_budget: int = 3
    execution_retry_budget: int = 10
    time_budget_s: float = 30.0
    action_budget: int = 20
    risk_budget: int = 5
    elapsed_time_s: float = 0.0
    actions_used: int = 0
    step_retries_used: dict[str, int] = field(default_factory=dict)
    total_retries_used: int = 0
    risk_consumed: int = 0

    def can_attempt_step_recovery(self, step_id: str, action_cost: int = 1, risk_cost: int = 1) -> bool:
        """Evaluate if sufficient budget remains for a step recovery attempt."""
        retries_for_step = self.step_retries_used.get(step_id, 0)
        if retries_for_step >= self.step_retry_budget:
            return False
        if self.total_retries_used >= self.execution_retry_budget:
            return False
        if self.elapsed_time_s >= self.time_budget_s:
            return False
        if (self.actions_used + action_cost) > self.action_budget:
            return False
        if (self.risk_consumed + risk_cost) > self.risk_budget:
            return False
        return True

    def consume(self, step_id: str, elapsed_s: float, action_cost: int = 1, risk_cost: int = 1) -> None:
        """Consume recovery budget units."""
        self.step_retries_used[step_id] = self.step_retries_used.get(step_id, 0) + 1
        self.total_retries_used += 1
        self.elapsed_time_s += elapsed_s
        self.actions_used += action_cost
        self.risk_consumed += risk_cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_retry_budget": self.step_retry_budget,
            "execution_retry_budget": self.execution_retry_budget,
            "time_budget_s": self.time_budget_s,
            "action_budget": self.action_budget,
            "risk_budget": self.risk_budget,
            "elapsed_time_s": round(self.elapsed_time_s, 2),
            "actions_used": self.actions_used,
            "step_retries_used": dict(self.step_retries_used),
            "total_retries_used": self.total_retries_used,
            "risk_consumed": self.risk_consumed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryBudget":
        return cls(**data)


@dataclass
class RecoveryPlan:
    """Pre-computed, validated recovery execution plan."""

    plan_id: str
    failure_id: str
    recovery_strategy: RecoveryStrategy
    candidate_actions: list[PlannedAction] = field(default_factory=list)
    confidence: float = 1.0
    risk: SafetyLevel = SafetyLevel.SAFE
    budget_cost: int = 1
    expected_state: dict[str, Any] = field(default_factory=dict)
    abort_conditions: list[str] = field(default_factory=list)
    explanation: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "failure_id": self.failure_id,
            "recovery_strategy": str(self.recovery_strategy),
            "candidate_actions": [a.to_dict() for a in self.candidate_actions],
            "confidence": round(self.confidence, 4),
            "risk": str(self.risk),
            "budget_cost": self.budget_cost,
            "expected_state": self.expected_state,
            "abort_conditions": self.abort_conditions,
            "explanation": self.explanation,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryPlan":
        d = dict(data)
        d["recovery_strategy"] = RecoveryStrategy(d["recovery_strategy"])
        d["risk"] = SafetyLevel(d.get("risk", "SAFE"))
        d["candidate_actions"] = [PlannedAction.from_dict(a) for a in d.get("candidate_actions", [])]
        return cls(**d)


@dataclass
class RecoveryAttempt:
    """Auditable record of a single recovery execution attempt."""

    attempt_id: str
    failure_id: str
    strategy: RecoveryStrategy
    before_state: dict[str, Any]
    action: Optional[PlannedAction]
    after_state: dict[str, Any]
    verification_passed: bool
    result: str
    confidence: float
    risk: SafetyLevel
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "failure_id": self.failure_id,
            "strategy": str(self.strategy),
            "before_state": self.before_state,
            "action": self.action.to_dict() if self.action else None,
            "after_state": self.after_state,
            "verification_passed": self.verification_passed,
            "result": self.result,
            "confidence": round(self.confidence, 4),
            "risk": str(self.risk),
            "duration_ms": round(self.duration_ms, 2),
            "error_message": self.error_message,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryAttempt":
        d = dict(data)
        d["strategy"] = RecoveryStrategy(d["strategy"])
        d["risk"] = SafetyLevel(d.get("risk", "SAFE"))
        if d.get("action"):
            d["action"] = PlannedAction.from_dict(d["action"])
        return cls(**d)
