"""Canonical Skill Intermediate Representation (Skill IR) schemas for Phase 8.

Defines the structured, portable, validated representation of WHAT a skill does,
WHAT it expects, WHAT it operates on, and HOW each semantic step is grounded,
strictly without performing or embedding executable operations.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class SkillActionType(str, Enum):
    """Semantic action types supported in the Skill IR."""

    OPEN = "OPEN"
    CLOSE = "CLOSE"
    SELECT = "SELECT"
    INPUT = "INPUT"
    EDIT = "EDIT"
    NAVIGATE = "NAVIGATE"
    ACTIVATE = "ACTIVATE"
    SAVE = "SAVE"
    CREATE = "CREATE"
    DELETE = "DELETE"
    MOVE = "MOVE"
    RENAME = "RENAME"
    COPY = "COPY"
    PASTE = "PASTE"
    SUBMIT = "SUBMIT"
    WAIT_FOR_STATE = "WAIT_FOR_STATE"
    VERIFY_STATE = "VERIFY_STATE"

    def __str__(self) -> str:
        return self.value


class ParameterType(str, Enum):
    """Data types for extracted skill parameters."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    FILE = "file"
    FOLDER = "folder"
    APPLICATION = "application"
    URL = "url"
    TEXT = "text"
    SELECTION = "selection"
    ENTITY_REFERENCE = "entity_reference"

    def __str__(self) -> str:
        return self.value


class ValueClassification(str, Enum):
    """Categorization of literal values discovered during demonstration."""

    CONSTANT = "CONSTANT"
    PARAMETER = "PARAMETER"
    ENVIRONMENTAL_VALUE = "ENVIRONMENTAL_VALUE"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


class GroundingStrategy(str, Enum):
    """Strategies for resolving targets in the user interface."""

    ACCESSIBILITY = "ACCESSIBILITY"
    OCR_TEXT = "OCR_TEXT"
    UI_ROLE = "UI_ROLE"
    WINDOW = "WINDOW"
    APPLICATION = "APPLICATION"
    VISUAL_REGION = "VISUAL_REGION"
    ENTITY_STATE = "ENTITY_STATE"
    SEMANTIC_CONTEXT = "SEMANTIC_CONTEXT"

    def __str__(self) -> str:
        return self.value


class CompilationStatus(str, Enum):
    """Semantic compilation status of the Skill IR."""

    COMPILED = "COMPILED"
    COMPILED_WITH_WARNINGS = "COMPILED_WITH_WARNINGS"
    NEEDS_DISAMBIGUATION = "NEEDS_DISAMBIGUATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"

    def __str__(self) -> str:
        return self.value


class FailureConditionType(str, Enum):
    """Categorization of expected or known failure modes."""

    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    APPLICATION_UNAVAILABLE = "APPLICATION_UNAVAILABLE"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    EXPECTED_STATE_NOT_REACHED = "EXPECTED_STATE_NOT_REACHED"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    def __str__(self) -> str:
        return self.value


@dataclass
class SkillParameter:
    """An explicit input parameter required or accepted by the skill."""

    parameter_id: str
    name: str
    type: ParameterType
    description: str
    required: bool = True
    default: Optional[Any] = None
    example_value: Optional[Any] = None
    classification: ValueClassification = ValueClassification.PARAMETER
    source_evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = str(self.type)
        d["classification"] = str(self.classification)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillParameter":
        d = dict(data)
        d["type"] = ParameterType(d["type"])
        d["classification"] = ValueClassification(d["classification"])
        return cls(**d)


@dataclass
class SkillVariable:
    """An internal semantic state variable within the skill lifetime."""

    variable_id: str
    name: str
    type: str
    source: str
    lifetime: str = "skill_execution"
    initial_value: Optional[Any] = None
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillVariable":
        return cls(**data)


@dataclass
class GroundingRequirement:
    """Future perceptual and accessibility evidence requirements to locate a target."""

    target_name: str
    semantic_label: str
    element_type: str = "UI_CONTROL"
    application: Optional[str] = None
    preferred_strategy: GroundingStrategy = GroundingStrategy.ACCESSIBILITY
    fallback_strategies: list[GroundingStrategy] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["preferred_strategy"] = str(self.preferred_strategy)
        d["fallback_strategies"] = [str(s) for s in self.fallback_strategies]
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundingRequirement":
        d = dict(data)
        d["preferred_strategy"] = GroundingStrategy(d["preferred_strategy"])
        d["fallback_strategies"] = [GroundingStrategy(s) for s in d.get("fallback_strategies", [])]
        return cls(**d)


@dataclass
class VerificationRequirement:
    """State verification required after a step."""

    description: str
    expected_state: str
    evidence_required: list[str] = field(default_factory=list)
    timeout_ms: float = 5000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationRequirement":
        return cls(**data)


@dataclass
class SkillStep:
    """A portable, non-executing semantic step in the Skill IR."""

    step_id: str
    ordinal: int
    action_type: SkillActionType
    target: str
    description: str
    arguments: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    grounding: Optional[GroundingRequirement] = None
    verification: Optional[VerificationRequirement] = None
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0
    optional: bool = False
    source_semantic_action_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "ordinal": self.ordinal,
            "action_type": str(self.action_type),
            "target": self.target,
            "description": self.description,
            "arguments": self.arguments,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "grounding": self.grounding.to_dict() if self.grounding else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "evidence_refs": self.evidence_refs,
            "confidence": round(self.confidence, 4),
            "optional": self.optional,
            "source_semantic_action_id": self.source_semantic_action_id,
        }

    @property
    def parameters(self) -> dict[str, Any]:
        return self.arguments

    @property
    def target_element(self) -> str:
        return self.target

    @property
    def intent(self) -> str:
        return self.description

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillStep":
        d = dict(data)
        d["action_type"] = SkillActionType(d["action_type"])
        if d.get("grounding"):
            d["grounding"] = GroundingRequirement.from_dict(d["grounding"])
        if d.get("verification"):
            d["verification"] = VerificationRequirement.from_dict(d["verification"])
        return cls(**d)


@dataclass
class SkillCheckpoint:
    """Explicit semantic milestone or verification boundary."""

    checkpoint_id: str
    after_step_id: str
    description: str
    expected_state: str
    evidence_requirement: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillCheckpoint":
        return cls(**data)


@dataclass
class SkillPrecondition:
    """Precondition required prior to skill initiation."""

    precondition_id: str
    precondition_type: str
    description: str
    target: str = ""
    observed: bool = True
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillPrecondition":
        return cls(**data)


@dataclass
class SkillPostcondition:
    """Observable condition that must hold after successful skill execution."""

    postcondition_id: str
    postcondition_type: str
    description: str
    target: str = ""
    observed: bool = True
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillPostcondition":
        return cls(**data)


@dataclass
class SkillDependency:
    """Environmental dependency (application, OS feature, file system)."""

    dependency_id: str
    dependency_type: str  # application, os, permission, path
    name: str
    required: bool = True
    description: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillDependency":
        return cls(**data)


@dataclass
class SkillFailureCondition:
    """Identified condition under which the skill should abort."""

    condition_id: str
    condition_type: FailureConditionType
    description: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["condition_type"] = str(self.condition_type)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillFailureCondition":
        d = dict(data)
        d["condition_type"] = FailureConditionType(d["condition_type"])
        return cls(**d)


@dataclass
class SkillIR:
    """Canonical Skill Intermediate Representation.
    
    Complete, validated, portable, and non-executing specification of a learned skill.
    """

    skill_id: str
    name: str
    description: str
    intent_type: str
    goal: str
    schema_version: str = "1.0.0"
    status: CompilationStatus = CompilationStatus.COMPILED
    parameters: list[SkillParameter] = field(default_factory=list)
    variables: list[SkillVariable] = field(default_factory=list)
    dependencies: list[SkillDependency] = field(default_factory=list)
    preconditions: list[SkillPrecondition] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)
    checkpoints: list[SkillCheckpoint] = field(default_factory=list)
    postconditions: list[SkillPostcondition] = field(default_factory=list)
    failure_conditions: list[SkillFailureCondition] = field(default_factory=list)
    grounding_requirements: list[GroundingRequirement] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    compiler_info: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_canonical_fingerprint(self) -> str:
        """Compute deterministic SHA-256 fingerprint over semantic core fields.
        
        Excludes volatile execution fields (timestamps, process IDs, local paths).
        """
        canonical_payload = {
            "name": self.name,
            "intent_type": self.intent_type,
            "goal": self.goal,
            "schema_version": self.schema_version,
            "parameters": [p.to_dict() for p in sorted(self.parameters, key=lambda x: x.parameter_id)],
            "variables": [v.to_dict() for v in sorted(self.variables, key=lambda x: x.variable_id)],
            "dependencies": [d.to_dict() for d in sorted(self.dependencies, key=lambda x: x.dependency_id)],
            "preconditions": [pr.to_dict() for pr in sorted(self.preconditions, key=lambda x: x.precondition_id)],
            "steps": [s.to_dict() for s in sorted(self.steps, key=lambda x: x.ordinal)],
            "checkpoints": [c.to_dict() for c in sorted(self.checkpoints, key=lambda x: x.checkpoint_id)],
            "postconditions": [po.to_dict() for po in sorted(self.postconditions, key=lambda x: x.postcondition_id)],
            "failure_conditions": [f.to_dict() for f in sorted(self.failure_conditions, key=lambda x: x.condition_id)],
        }
        serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def version(self) -> str:
        return self.schema_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "intent_type": self.intent_type,
            "goal": self.goal,
            "schema_version": self.schema_version,
            "status": str(self.status),
            "parameters": [p.to_dict() for p in self.parameters],
            "variables": [v.to_dict() for v in self.variables],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "preconditions": [pr.to_dict() for pr in self.preconditions],
            "steps": [s.to_dict() for s in self.steps],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "postconditions": [po.to_dict() for po in self.postconditions],
            "failure_conditions": [f.to_dict() for f in self.failure_conditions],
            "grounding_requirements": [g.to_dict() for g in self.grounding_requirements],
            "evidence_refs": self.evidence_refs,
            "confidence": round(self.confidence, 4),
            "ambiguities": self.ambiguities,
            "provenance": self.provenance,
            "compiler_info": self.compiler_info,
            "fingerprint": self.fingerprint,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillIR":
        d = dict(data)
        d["status"] = CompilationStatus(d["status"])
        d["parameters"] = [SkillParameter.from_dict(p) for p in d.get("parameters", [])]
        d["variables"] = [SkillVariable.from_dict(v) for v in d.get("variables", [])]
        d["dependencies"] = [SkillDependency.from_dict(dep) for dep in d.get("dependencies", [])]
        d["preconditions"] = [SkillPrecondition.from_dict(pr) for pr in d.get("preconditions", [])]
        d["steps"] = [SkillStep.from_dict(s) for s in d.get("steps", [])]
        d["checkpoints"] = [SkillCheckpoint.from_dict(c) for c in d.get("checkpoints", [])]
        d["postconditions"] = [SkillPostcondition.from_dict(po) for po in d.get("postconditions", [])]
        d["failure_conditions"] = [SkillFailureCondition.from_dict(f) for f in d.get("failure_conditions", [])]
        d["grounding_requirements"] = [GroundingRequirement.from_dict(g) for g in d.get("grounding_requirements", [])]
        return cls(**d)


@dataclass
class SkillManifest:
    """Compilation summary manifest and integrity ledger for Phase 8."""

    manifest_id: str
    skill_id: str
    session_id: str
    schema_version: str = "1.0.0"
    compiler_id: str = "deterministic_skill_compiler"
    compiler_version: str = "1.0.0"
    status: str = "COMPILED"
    total_steps: int = 0
    total_parameters: int = 0
    total_variables: int = 0
    total_checkpoints: int = 0
    total_dependencies: int = 0
    overall_confidence: float = 1.0
    fingerprint: str = ""
    compilation_duration_sec: float = 0.0
    source_checksums: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        return cls(**data)
