"""Canonical data models, contracts, and policies for Phase 13 Learning & Skill Improvement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class VariationType(str, Enum):
    """Classification of detected environmental or UI variation."""

    COSMETIC_CHANGE = "cosmetic_change"
    GEOMETRIC_CHANGE = "geometric_change"
    SEMANTICALLY_EQUIVALENT_CHANGE = "semantically_equivalent_change"
    SEMANTIC_CHANGE = "semantic_change"
    UNKNOWN_CHANGE = "unknown_change"

    def __str__(self) -> str:
        return self.value


class PromotionMode(str, Enum):
    """Enforcement mode for skill version promotion."""

    AUTOMATIC_SAFE = "automatic_safe"
    SUPERVISED = "supervised"
    MANUAL_ONLY = "manual_only"

    def __str__(self) -> str:
        return self.value


class VersionChangeType(str, Enum):
    """Semantic versioning impact."""

    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"
    CONFLICT = "conflict"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ExecutionRecord:
    """Canonical record of a single skill execution run."""

    execution_id: str
    skill_id: str
    skill_version: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    hardware_profile: dict[str, Any] = field(default_factory=dict)
    environment_signature: str = "default_env"
    steps_total: int = 1
    steps_successful: int = 1
    steps_failed: int = 0
    recovery_attempts: int = 0
    recovery_successes: int = 0
    execution_duration: float = 0.5
    verification_results: list[dict[str, Any]] = field(default_factory=list)
    final_outcome: str = "SUCCESS"  # "SUCCESS", "RECOVERED", "FAILED", "CANCELLED"
    failure_types: list[str] = field(default_factory=list)
    grounding_confidence: float = 1.0
    recovery_confidence: float = 1.0
    user_intervention: bool = False
    privacy_classification: str = "LOCAL_CONFIDENTIAL"
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def compute_fingerprint(self) -> str:
        payload = {
            "execution_id": self.execution_id,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "timestamp": self.timestamp,
            "final_outcome": self.final_outcome,
            "failure_types": sorted(self.failure_types),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PerformanceMetrics:
    """Aggregated numerical performance indicators for a skill."""

    sample_count: int = 0
    success_rate: float = 0.0
    verified_success_rate: float = 0.0
    failure_rate: float = 0.0
    recovery_rate: float = 0.0
    mean_execution_time: float = 0.0
    median_execution_time: float = 0.0
    p95_execution_time: float = 0.0
    grounding_success_rate: float = 0.0
    postcondition_success_rate: float = 0.0
    manual_intervention_rate: float = 0.0
    retry_rate: float = 0.0
    rollback_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillPerformanceProfile:
    """Tracked historical performance distribution for a skill version."""

    skill_id: str
    version: str
    sample_count: int
    metrics: PerformanceMetrics
    failure_distribution: dict[str, int] = field(default_factory=dict)
    recovery_distribution: dict[str, int] = field(default_factory=dict)
    environment_distribution: dict[str, int] = field(default_factory=dict)
    hardware_distribution: dict[str, int] = field(default_factory=dict)
    confidence_distribution: dict[str, int] = field(default_factory=dict)
    performance_trend: str = "STABLE"  # "IMPROVING", "STABLE", "DEGRADING", "DRIFT_DETECTED"
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["metrics"] = self.metrics.to_dict()
        return data


@dataclass(frozen=True)
class FailurePattern:
    """Recurring failure pattern identified across multiple executions."""

    pattern_id: str
    pattern_type: str  # e.g. "TARGET_MOVED", "FOCUS_LOST", "TIMEOUT"
    skill_id: str
    affected_step: str
    frequency: int
    sample_count: int
    environment_signature: str
    common_recovery_strategy: Optional[str] = None
    confidence: float = 0.8
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentVariation:
    """Detected variation in host UI, geometry, or application state."""

    variation_id: str
    skill_id: str
    variation_type: VariationType
    attribute_changed: str
    base_value: str
    observed_value: str
    frequency: int
    impact_score: float = 0.0  # 0.0 (benign) to 1.0 (breaking)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["variation_type"] = self.variation_type.value
        return data


@dataclass(frozen=True)
class ImprovementProposal:
    """Evidence-backed improvement proposal for a skill."""

    proposal_id: str
    skill_id: str
    base_version: str
    reason: str
    evidence_refs: list[str]
    affected_steps: list[str]
    proposed_change: dict[str, Any]
    expected_benefit: str
    risk: str = "LOW"  # "LOW", "MEDIUM", "HIGH"
    confidence: float = 0.85
    required_validation: list[str] = field(default_factory=lambda: ["shadow_eval", "schema_check"])
    status: str = "PROPOSED"  # "PROPOSED", "VALIDATED", "REJECTED", "PROMOTED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def compute_fingerprint(self) -> str:
        payload = {
            "skill_id": self.skill_id,
            "base_version": self.base_version,
            "reason": self.reason,
            "affected_steps": sorted(self.affected_steps),
            "proposed_change": self.proposed_change,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateSkillVersion:
    """A proposed, immutable candidate SkillVersion generated from verified proposals."""

    candidate_id: str
    skill_id: str
    base_version: str
    candidate_version: str
    fingerprint: str
    diff: dict[str, Any]
    reason: str
    evidence_refs: list[str]
    skill_ir: dict[str, Any]
    validation_results: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_promoted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionPolicy:
    """Explicit guard policy governing when candidates may be promoted."""

    mode: PromotionMode = PromotionMode.SUPERVISED
    minimum_executions: int = 5
    minimum_failures: int = 2
    minimum_success_improvement: float = 0.05
    maximum_regression: float = 0.0
    minimum_verification_confidence: float = 0.85
    maximum_failure_rate: float = 0.20
    maximum_recovery_increase: float = 0.10
    maximum_resource_increase_mb: int = 128
    maximum_latency_increase_ms: float = 500.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


@dataclass(frozen=True)
class LearningBudget:
    """Resource constraints bounding learning storage and cycle complexity."""

    max_records: int = 10000
    max_candidates: int = 10
    max_experiments: int = 5
    max_runtime_s: float = 30.0
    max_storage_mb: int = 500
    max_model_calls: int = 50

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningExperiment:
    """Structured scientific record of a candidate version shadow/canary experiment."""

    experiment_id: str
    skill_id: str
    base_version: str
    candidate_version: str
    hypothesis: str
    sample_policy: str
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any]
    decision: str  # "PROMOTE", "REJECT", "CONTINUE_TESTING"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningAudit:
    """Audit log entry recording an improvement, promotion, or rollback event."""

    audit_id: str
    action: str  # "RECORD_INGESTED", "PROPOSAL_CREATED", "CANDIDATE_GENERATED", "PROMOTED", "ROLLED_BACK"
    skill_id: str
    operator_policy: str
    evidence_summary: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
