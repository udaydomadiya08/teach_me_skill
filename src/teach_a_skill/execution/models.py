"""Phase 10 data models for execution, grounding, and session management.

All models are portable dataclasses with full serialization/deserialization.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExecutionPolicy(str, Enum):
    """Execution mode controlling whether real actions are performed."""

    DRY_RUN = "DRY_RUN"
    SUPERVISED = "SUPERVISED"
    AUTONOMOUS = "AUTONOMOUS"

    def __str__(self) -> str:
        return self.value


class ExecutionState(str, Enum):
    """Lifecycle state of an execution session."""

    CREATED = "CREATED"
    GROUNDING = "GROUNDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"

    def __str__(self) -> str:
        return self.value


class StepStatus(str, Enum):
    """Execution status of a single skill step."""

    PENDING = "PENDING"
    GROUNDING = "GROUNDING"
    GROUNDED = "GROUNDED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"

    def __str__(self) -> str:
        return self.value


class GroundingMatchType(str, Enum):
    """How a target was resolved in the live environment."""

    ACCESSIBILITY = "ACCESSIBILITY"
    OCR_TEXT = "OCR_TEXT"
    UI_ROLE = "UI_ROLE"
    WINDOW = "WINDOW"
    APPLICATION = "APPLICATION"
    VISUAL_REGION = "VISUAL_REGION"
    SEMANTIC_CONTEXT = "SEMANTIC_CONTEXT"
    COMBINED = "COMBINED"
    NONE = "NONE"

    def __str__(self) -> str:
        return self.value


class ActionType(str, Enum):
    """Low-level platform action types."""

    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    TYPE_TEXT = "TYPE_TEXT"
    KEY_PRESS = "KEY_PRESS"
    KEY_COMBO = "KEY_COMBO"
    SCROLL = "SCROLL"
    DRAG = "DRAG"
    FOCUS = "FOCUS"
    WAIT = "WAIT"
    ACTIVATE_WINDOW = "ACTIVATE_WINDOW"
    ACTIVATE_APP = "ACTIVATE_APP"
    NOOP = "NOOP"

    def __str__(self) -> str:
        return self.value


class SafetyLevel(str, Enum):
    """Risk classification of an action."""

    SAFE = "SAFE"
    MODERATE = "MODERATE"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Grounding models
# ---------------------------------------------------------------------------


@dataclass
class GroundingCandidate:
    """A candidate UI element matched from the live environment."""

    candidate_id: str
    target_name: str
    match_type: GroundingMatchType
    confidence: float
    pixel_x: float = 0.0
    pixel_y: float = 0.0
    pixel_width: float = 0.0
    pixel_height: float = 0.0
    normalized_x: float = 0.0
    normalized_y: float = 0.0
    normalized_width: float = 0.0
    normalized_height: float = 0.0
    text_content: Optional[str] = None
    element_role: Optional[str] = None
    application: Optional[str] = None
    window_title: Optional[str] = None
    accessibility_label: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["match_type"] = str(self.match_type)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundingCandidate":
        d = dict(data)
        d["match_type"] = GroundingMatchType(d["match_type"])
        return cls(**d)


@dataclass
class GroundingResult:
    """Result of grounding a single Skill IR step target."""

    step_id: str
    target_name: str
    grounded: bool
    best_candidate: Optional[GroundingCandidate] = None
    all_candidates: list[GroundingCandidate] = field(default_factory=list)
    confidence: float = 0.0
    ambiguous: bool = False
    explanation: str = ""
    strategies_attempted: list[str] = field(default_factory=list)
    timing_ms: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "target_name": self.target_name,
            "grounded": self.grounded,
            "best_candidate": self.best_candidate.to_dict() if self.best_candidate else None,
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "confidence": round(self.confidence, 4),
            "ambiguous": self.ambiguous,
            "explanation": self.explanation,
            "strategies_attempted": self.strategies_attempted,
            "timing_ms": round(self.timing_ms, 2),
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundingResult":
        d = dict(data)
        if d.get("best_candidate"):
            d["best_candidate"] = GroundingCandidate.from_dict(d["best_candidate"])
        d["all_candidates"] = [GroundingCandidate.from_dict(c) for c in d.get("all_candidates", [])]
        return cls(**d)


# ---------------------------------------------------------------------------
# Execution plan models
# ---------------------------------------------------------------------------


@dataclass
class PlannedAction:
    """A concrete platform action derived from a Skill IR step + grounding."""

    action_id: str
    step_id: str
    action_type: ActionType
    target_x: float = 0.0
    target_y: float = 0.0
    text_input: Optional[str] = None
    key_sequence: Optional[str] = None
    duration_ms: float = 0.0
    safety_level: SafetyLevel = SafetyLevel.SAFE
    description: str = ""
    grounding_confidence: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action_type"] = str(self.action_type)
        d["safety_level"] = str(self.safety_level)
        d["grounding_confidence"] = round(self.grounding_confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannedAction":
        d = dict(data)
        d["action_type"] = ActionType(d["action_type"])
        d["safety_level"] = SafetyLevel(d["safety_level"])
        return cls(**d)


@dataclass
class ExecutionPlan:
    """Complete, validated execution plan for a skill."""

    plan_id: str
    skill_id: str
    skill_version: str
    policy: ExecutionPolicy
    planned_actions: list[PlannedAction] = field(default_factory=list)
    grounding_results: list[GroundingResult] = field(default_factory=list)
    all_grounded: bool = False
    minimum_confidence: float = 0.0
    overall_safety: SafetyLevel = SafetyLevel.SAFE
    preconditions_met: bool = False
    ready_to_execute: bool = False
    explanation: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_fingerprint(self) -> str:
        payload = {
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "policy": str(self.policy),
            "actions": [a.to_dict() for a in self.planned_actions],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "policy": str(self.policy),
            "planned_actions": [a.to_dict() for a in self.planned_actions],
            "grounding_results": [g.to_dict() for g in self.grounding_results],
            "all_grounded": self.all_grounded,
            "minimum_confidence": round(self.minimum_confidence, 4),
            "overall_safety": str(self.overall_safety),
            "preconditions_met": self.preconditions_met,
            "ready_to_execute": self.ready_to_execute,
            "explanation": self.explanation,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionPlan":
        d = dict(data)
        d["policy"] = ExecutionPolicy(d["policy"])
        d["overall_safety"] = SafetyLevel(d["overall_safety"])
        d["planned_actions"] = [PlannedAction.from_dict(a) for a in d.get("planned_actions", [])]
        d["grounding_results"] = [GroundingResult.from_dict(g) for g in d.get("grounding_results", [])]
        return cls(**d)


# ---------------------------------------------------------------------------
# Step execution result
# ---------------------------------------------------------------------------


@dataclass
class StepExecutionResult:
    """Outcome of executing a single planned action."""

    step_id: str
    action_id: str
    status: StepStatus
    action_type: ActionType
    was_dry_run: bool = True
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float = 0.0
    verification_passed: Optional[bool] = None
    verification_details: dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    rollback_available: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        d["action_type"] = str(self.action_type)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepExecutionResult":
        d = dict(data)
        d["status"] = StepStatus(d["status"])
        d["action_type"] = ActionType(d["action_type"])
        return cls(**d)


# ---------------------------------------------------------------------------
# Execution session
# ---------------------------------------------------------------------------


@dataclass
class ExecutionCheckpoint:
    """Snapshot of execution state at a specific step boundary."""

    checkpoint_id: str
    session_id: str
    after_step_index: int
    state: ExecutionState
    completed_steps: list[str] = field(default_factory=list)
    remaining_steps: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = str(self.state)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionCheckpoint":
        d = dict(data)
        d["state"] = ExecutionState(d["state"])
        return cls(**d)


@dataclass
class ExecutionSession:
    """Full lifecycle record of a skill execution attempt."""

    session_id: str
    skill_id: str
    skill_version: str
    policy: ExecutionPolicy
    state: ExecutionState = ExecutionState.CREATED
    plan: Optional[ExecutionPlan] = None
    step_results: list[StepExecutionResult] = field(default_factory=list)
    checkpoints: list[ExecutionCheckpoint] = field(default_factory=list)
    current_step_index: int = 0
    total_steps: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    total_duration_ms: float = 0.0
    error_message: Optional[str] = None
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "policy": str(self.policy),
            "state": str(self.state),
            "plan": self.plan.to_dict() if self.plan else None,
            "step_results": [r.to_dict() for r in self.step_results],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "current_step_index": self.current_step_index,
            "total_steps": self.total_steps,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "error_message": self.error_message,
            "cancelled": self.cancelled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionSession":
        d = dict(data)
        d["policy"] = ExecutionPolicy(d["policy"])
        d["state"] = ExecutionState(d["state"])
        if d.get("plan"):
            d["plan"] = ExecutionPlan.from_dict(d["plan"])
        d["step_results"] = [StepExecutionResult.from_dict(r) for r in d.get("step_results", [])]
        d["checkpoints"] = [ExecutionCheckpoint.from_dict(c) for c in d.get("checkpoints", [])]
        return cls(**d)


# ---------------------------------------------------------------------------
# Environment snapshot
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentElement:
    """A UI element observed in the current live environment."""

    element_id: str
    role: str  # button, text_field, label, menu_item, checkbox, etc.
    label: Optional[str] = None
    title: Optional[str] = None
    value: Optional[str] = None
    enabled: bool = True
    focused: bool = False
    visible: bool = True
    pixel_x: float = 0.0
    pixel_y: float = 0.0
    pixel_width: float = 0.0
    pixel_height: float = 0.0
    application: Optional[str] = None
    window_title: Optional[str] = None
    depth: int = 0
    children_count: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentElement":
        return cls(**data)


@dataclass
class EnvironmentSnapshot:
    """Point-in-time observation of the user's desktop environment."""

    snapshot_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    active_application: Optional[str] = None
    active_window_title: Optional[str] = None
    running_applications: list[str] = field(default_factory=list)
    elements: list[EnvironmentElement] = field(default_factory=list)
    screen_width: int = 1920
    screen_height: int = 1080
    scale_factor: float = 1.0
    ocr_text_regions: list[dict[str, Any]] = field(default_factory=list)
    observation_duration_ms: float = 0.0
    source: str = "synthetic"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "active_application": self.active_application,
            "active_window_title": self.active_window_title,
            "running_applications": self.running_applications,
            "elements": [e.to_dict() for e in self.elements],
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "scale_factor": self.scale_factor,
            "ocr_text_regions": self.ocr_text_regions,
            "observation_duration_ms": round(self.observation_duration_ms, 2),
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentSnapshot":
        d = dict(data)
        d["elements"] = [EnvironmentElement.from_dict(e) for e in d.get("elements", [])]
        return cls(**d)


# ---------------------------------------------------------------------------
# Execution manifest
# ---------------------------------------------------------------------------


@dataclass
class ExecutionManifest:
    """Persistent manifest summarizing an execution session."""

    manifest_id: str
    session_id: str
    skill_id: str
    skill_version: str
    policy: str
    state: str
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_duration_ms: float = 0.0
    overall_confidence: float = 0.0
    all_verified: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionManifest":
        return cls(**data)
