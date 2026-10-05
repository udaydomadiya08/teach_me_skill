"""Structured canonical schemas for Phase 7: Intent & Demonstration Understanding."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class IntentType(str, Enum):
    """Categorization of demonstrated intent types."""

    SAVE_DOCUMENT = "SAVE_DOCUMENT"
    OPEN_DOCUMENT = "OPEN_DOCUMENT"
    EDIT_TEXT = "EDIT_TEXT"
    NAVIGATE_APPLICATION = "NAVIGATE_APPLICATION"
    SWITCH_WINDOW = "SWITCH_WINDOW"
    SEARCH_QUERY = "SEARCH_QUERY"
    FORM_SUBMISSION = "FORM_SUBMISSION"
    CLOSE_WINDOW = "CLOSE_WINDOW"
    CUSTOM_INTERACTION = "CUSTOM_INTERACTION"

    def __str__(self) -> str:
        return self.value


class ActionType(str, Enum):
    """Semantic action taxonomy grounded in physical and perceptual evidence."""

    ACTIVATE_CONTROL = "ACTIVATE_CONTROL"
    INPUT_TEXT = "INPUT_TEXT"
    SWITCH_APPLICATION = "SWITCH_APPLICATION"
    FOCUS_WINDOW = "FOCUS_WINDOW"
    NAVIGATE_VIEW = "NAVIGATE_VIEW"
    SELECT_OPTION = "SELECT_OPTION"
    HOTKEY_ACTION = "HOTKEY_ACTION"
    INSPECT_REGION = "INSPECT_REGION"

    def __str__(self) -> str:
        return self.value


class StateTransitionType(str, Enum):
    """Certainty level of observed or inferred state transitions."""

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"

    def __str__(self) -> str:
        return self.value


@dataclass
class Precondition:
    """Observable condition required prior to task or stage execution."""

    description: str
    observed: bool = True
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Precondition":
        return cls(**data)


@dataclass
class Postcondition:
    """Observable or inferred resulting state after task or stage completion."""

    description: str
    observed: bool = True
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Postcondition":
        return cls(**data)


@dataclass
class TaskEntity:
    """Task-relevant entity referenced during the demonstration with evidence provenance."""

    entity_id: str
    entity_type: str  # e.g., "application", "document", "button", "window"
    label: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEntity":
        return cls(**data)


@dataclass
class StateTransition:
    """Observable or inferred transition between UI/environment states."""

    transition_id: str
    description: str
    before_state: str
    after_state: str
    transition_type: StateTransitionType = StateTransitionType.OBSERVED
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["transition_type"] = str(self.transition_type)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateTransition":
        data_copy = dict(data)
        data_copy["transition_type"] = StateTransitionType(data_copy["transition_type"])
        return cls(**data_copy)


@dataclass
class TaskAmbiguity:
    """Explicit representation of ambiguous or competing task interpretations."""

    ambiguity_id: str
    description: str
    interpretations: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskAmbiguity":
        return cls(**data)


@dataclass
class SemanticAction:
    """Semantic meaning of demonstrated physical interactions grounded in evidence."""

    action_id: str
    action_type: ActionType
    description: str
    timestamp_ms: float
    confidence: float
    source_events: list[str] = field(default_factory=list)
    target_entities: list[str] = field(default_factory=list)
    state_effects: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action_type"] = str(self.action_type)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticAction":
        data_copy = dict(data)
        data_copy["action_type"] = ActionType(data_copy["action_type"])
        return cls(**data_copy)


@dataclass
class TaskStage:
    """Coherent semantic milestone or stage within the demonstration timeline."""

    stage_id: str
    name: str
    description: str
    start_time_ms: float
    end_time_ms: float
    confidence: float
    action_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskStage":
        return cls(**data)


@dataclass
class DemonstratedIntent:
    """Inferred user intent grounded in multi-layer evidence with full lineage."""

    intent_id: str
    demonstration_id: str
    intent_type: IntentType
    goal: str
    task_name: str
    confidence: float
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    contradicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    ambiguities: list[TaskAmbiguity] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    preconditions: list[Precondition] = field(default_factory=list)
    postconditions: list[Postcondition] = field(default_factory=list)
    entities: list[TaskEntity] = field(default_factory=list)
    task_stages: list[str] = field(default_factory=list)
    model_provider: str = "deterministic"
    model_id: str = "deterministic_semantic_engine"
    model_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    fingerprint: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "demonstration_id": self.demonstration_id,
            "intent_type": str(self.intent_type),
            "goal": self.goal,
            "task_name": self.task_name,
            "confidence": round(self.confidence, 4),
            "evidence_refs": self.evidence_refs,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "ambiguities": [a.to_dict() for a in self.ambiguities],
            "alternatives": self.alternatives,
            "preconditions": [p.to_dict() for p in self.preconditions],
            "postconditions": [p.to_dict() for p in self.postconditions],
            "entities": [e.to_dict() for e in self.entities],
            "task_stages": self.task_stages,
            "model_provider": self.model_provider,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DemonstratedIntent":
        d = dict(data)
        d["intent_type"] = IntentType(d["intent_type"])
        d["ambiguities"] = [TaskAmbiguity.from_dict(a) for a in d.get("ambiguities", [])]
        d["preconditions"] = [Precondition.from_dict(p) for p in d.get("preconditions", [])]
        d["postconditions"] = [Postcondition.from_dict(p) for p in d.get("postconditions", [])]
        d["entities"] = [TaskEntity.from_dict(e) for e in d.get("entities", [])]
        return cls(**d)


@dataclass
class DemonstrationUnderstanding:
    """Holistic structured understanding of a recorded task demonstration."""

    task_id: str
    session_id: str
    task_name: str
    description: str
    goal: str
    confidence: float
    stages: list[TaskStage] = field(default_factory=list)
    actions: list[SemanticAction] = field(default_factory=list)
    entities: list[TaskEntity] = field(default_factory=list)
    state_transitions: list[StateTransition] = field(default_factory=list)
    preconditions: list[Precondition] = field(default_factory=list)
    postconditions: list[Postcondition] = field(default_factory=list)
    ambiguities: list[TaskAmbiguity] = field(default_factory=list)
    primary_intent: Optional[DemonstratedIntent] = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "task_name": self.task_name,
            "description": self.description,
            "goal": self.goal,
            "confidence": round(self.confidence, 4),
            "stages": [s.to_dict() for s in self.stages],
            "actions": [a.to_dict() for a in self.actions],
            "entities": [e.to_dict() for e in self.entities],
            "state_transitions": [t.to_dict() for t in self.state_transitions],
            "preconditions": [p.to_dict() for p in self.preconditions],
            "postconditions": [p.to_dict() for p in self.postconditions],
            "ambiguities": [a.to_dict() for a in self.ambiguities],
            "primary_intent": self.primary_intent.to_dict() if self.primary_intent else None,
            "evidence_refs": self.evidence_refs,
            "schema_version": self.schema_version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DemonstrationUnderstanding":
        d = dict(data)
        d["stages"] = [TaskStage.from_dict(s) for s in d.get("stages", [])]
        d["actions"] = [SemanticAction.from_dict(a) for a in d.get("actions", [])]
        d["entities"] = [TaskEntity.from_dict(e) for e in d.get("entities", [])]
        d["state_transitions"] = [StateTransition.from_dict(t) for t in d.get("state_transitions", [])]
        d["preconditions"] = [Precondition.from_dict(p) for p in d.get("preconditions", [])]
        d["postconditions"] = [Postcondition.from_dict(p) for p in d.get("postconditions", [])]
        d["ambiguities"] = [TaskAmbiguity.from_dict(a) for a in d.get("ambiguities", [])]
        if d.get("primary_intent"):
            d["primary_intent"] = DemonstratedIntent.from_dict(d["primary_intent"])
        return cls(**d)


@dataclass
class IntentManifest:
    """Summary manifest and integrity ledger for the Phase 7 intent partition."""

    manifest_id: str
    session_id: str
    schema_version: str = "1.0.0"
    derivation_version: str = "phase7-v1"
    provider_id: str = "deterministic"
    model_id: str = "deterministic_semantic_engine"
    total_stages: int = 0
    total_actions: int = 0
    total_entities: int = 0
    total_ambiguities: int = 0
    primary_intent_type: Optional[str] = None
    overall_confidence: float = 1.0
    processing_duration_sec: float = 0.0
    source_checksums: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IntentManifest":
        return cls(**data)
