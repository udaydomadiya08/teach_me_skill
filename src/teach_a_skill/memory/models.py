"""Canonical persistent Skill Format and Memory data models.

Phase 9 defines the persistent, versioned, lineage-preserving representation
of skills without any execution or runtime automation capabilities.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from teach_a_skill.skill.models import SkillIR


class SkillStatus(str, enum.Enum):
    """Lifecycle states for skills and skill versions."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    INVALID = "INVALID"
    CONFLICTED = "CONFLICTED"


class RelationshipType(str, enum.Enum):
    """Semantic relationship types between skills, versions, and demonstrations."""

    DERIVED_FROM = "DERIVED_FROM"
    SUPPORTED_BY = "SUPPORTED_BY"
    REVISION_OF = "REVISION_OF"
    SUPERSEDES = "SUPERSEDES"
    SUPERSEDED_BY = "SUPERSEDED_BY"
    DUPLICATE_OF = "DUPLICATE_OF"
    VARIANT_OF = "VARIANT_OF"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    GENERALIZES = "GENERALIZES"
    SPECIALIZES = "SPECIALIZES"


class VersionBump(str, enum.Enum):
    """Semantic version classification."""

    PATCH = "PATCH"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CONFLICT = "CONFLICT"


SEMVER_REGEX = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(version_str: str) -> tuple[int, int, int]:
    """Parse and validate a semantic version string."""
    m = SEMVER_REGEX.match(version_str.strip())
    if not m:
        raise ValueError(
            f"Invalid semantic version string '{version_str}'. Must follow MAJOR.MINOR.PATCH format."
        )
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def format_semver(major: int, minor: int, patch: int) -> str:
    """Format a semantic version tuple into string."""
    return f"{major}.{minor}.{patch}"


@dataclass
class DemonstrationLineageRecord:
    """Record of a source demonstration's relationship to a skill version."""

    demonstration_id: str
    skill_id: str
    skill_version: str
    relationship_type: RelationshipType = RelationshipType.DERIVED_FROM
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "demonstration_id": self.demonstration_id,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "relationship_type": self.relationship_type.value,
            "evidence_refs": list(self.evidence_refs),
            "confidence": round(self.confidence, 4),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DemonstrationLineageRecord:
        return cls(
            demonstration_id=data["demonstration_id"],
            skill_id=data["skill_id"],
            skill_version=data["skill_version"],
            relationship_type=RelationshipType(data.get("relationship_type", "DERIVED_FROM")),
            evidence_refs=list(data.get("evidence_refs", [])),
            confidence=float(data.get("confidence", 1.0)),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class SkillRelationshipRecord:
    """Explicit relationship between two skill versions."""

    source_skill_id: str
    source_version: str
    target_skill_id: str
    target_version: str
    relationship_type: RelationshipType
    reason: str
    confidence: float = 1.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_skill_id": self.source_skill_id,
            "source_version": self.source_version,
            "target_skill_id": self.target_skill_id,
            "target_version": self.target_version,
            "relationship_type": self.relationship_type.value,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillRelationshipRecord:
        return cls(
            source_skill_id=data["source_skill_id"],
            source_version=data["source_version"],
            target_skill_id=data["target_skill_id"],
            target_version=data["target_version"],
            relationship_type=RelationshipType(data["relationship_type"]),
            reason=data["reason"],
            confidence=float(data.get("confidence", 1.0)),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class SkillVersionRecord:
    """Immutable record for a specific published or archived skill version."""

    skill_id: str
    version: str
    status: SkillStatus
    fingerprint: str
    checksum: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    parent_version: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    source_demonstrations: list[str] = field(default_factory=list)
    skill_ir: Optional[SkillIR] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0.0"

    def compute_version_fingerprint(self) -> str:
        """Compute canonical deterministic SHA-256 fingerprint for this version."""
        if self.skill_ir:
            return self.skill_ir.compute_canonical_fingerprint()
        # Fallback to normalized metadata hash
        content = {
            "skill_id": self.skill_id,
            "version": self.version,
            "schema_version": self.schema_version,
            "metadata": self.metadata,
        }
        raw = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self, include_ir: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "skill_id": self.skill_id,
            "version": self.version,
            "status": self.status.value,
            "fingerprint": self.fingerprint,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "parent_version": self.parent_version,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "source_demonstrations": list(self.source_demonstrations),
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }
        if include_ir and self.skill_ir:
            d["skill_ir"] = self.skill_ir.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillVersionRecord:
        ir = None
        if "skill_ir" in data and data["skill_ir"]:
            ir = SkillIR.from_dict(data["skill_ir"])
        return cls(
            skill_id=data["skill_id"],
            version=data["version"],
            status=SkillStatus(data.get("status", "VALIDATED")),
            fingerprint=data.get("fingerprint", ""),
            checksum=data.get("checksum", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            parent_version=data.get("parent_version"),
            supersedes=data.get("supersedes"),
            superseded_by=data.get("superseded_by"),
            source_demonstrations=list(data.get("source_demonstrations", [])),
            skill_ir=ir,
            metadata=dict(data.get("metadata", {})),
            schema_version=data.get("schema_version", "1.0.0"),
        )


@dataclass
class RollbackRecord:
    """Audit record when current version is rolled back."""

    skill_id: str
    previous_current_version: str
    rollback_target: str
    rollback_reason: str
    rollback_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    operator: str = "user"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "previous_current_version": self.previous_current_version,
            "rollback_target": self.rollback_target,
            "rollback_reason": self.rollback_reason,
            "rollback_timestamp": self.rollback_timestamp,
            "operator": self.operator,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackRecord:
        return cls(
            skill_id=data["skill_id"],
            previous_current_version=data["previous_current_version"],
            rollback_target=data["rollback_target"],
            rollback_reason=data["rollback_reason"],
            rollback_timestamp=data.get(
                "rollback_timestamp", datetime.now(timezone.utc).isoformat()
            ),
            operator=data.get("operator", "user"),
        )


@dataclass
class SkillRecord:
    """Canonical persistent Skill Format top-level object."""

    skill_id: str
    canonical_name: str
    description: str
    status: SkillStatus = SkillStatus.DRAFT
    current_version: Optional[str] = None
    versions: list[str] = field(default_factory=list)
    source_demonstrations: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = "1.0.0"
    fingerprint: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "status": self.status.value,
            "current_version": self.current_version,
            "versions": list(self.versions),
            "source_demonstrations": list(self.source_demonstrations),
            "tags": list(self.tags),
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillRecord:
        return cls(
            skill_id=data["skill_id"],
            canonical_name=data["canonical_name"],
            description=data.get("description", ""),
            status=SkillStatus(data.get("status", "DRAFT")),
            current_version=data.get("current_version"),
            versions=list(data.get("versions", [])),
            source_demonstrations=list(data.get("source_demonstrations", [])),
            tags=list(data.get("tags", [])),
            capabilities=list(data.get("capabilities", [])),
            dependencies=list(data.get("dependencies", [])),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            schema_version=data.get("schema_version", "1.0.0"),
            fingerprint=data.get("fingerprint", ""),
            provenance=dict(data.get("provenance", {})),
        )


@dataclass
class VersionDiff:
    """Detailed semantic and structural comparison between two skill versions."""

    skill_id: str
    version_a: str
    version_b: str
    recommended_bump: VersionBump
    explanation: str
    semantic_changes: list[str] = field(default_factory=list)
    parameter_changes: list[str] = field(default_factory=list)
    step_changes: list[str] = field(default_factory=list)
    precondition_changes: list[str] = field(default_factory=list)
    postcondition_changes: list[str] = field(default_factory=list)
    grounding_changes: list[str] = field(default_factory=list)
    dependency_changes: list[str] = field(default_factory=list)
    confidence_delta: float = 0.0
    provenance_differences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version_a": self.version_a,
            "version_b": self.version_b,
            "recommended_bump": self.recommended_bump.value,
            "explanation": self.explanation,
            "semantic_changes": list(self.semantic_changes),
            "parameter_changes": list(self.parameter_changes),
            "step_changes": list(self.step_changes),
            "precondition_changes": list(self.precondition_changes),
            "postcondition_changes": list(self.postcondition_changes),
            "grounding_changes": list(self.grounding_changes),
            "dependency_changes": list(self.dependency_changes),
            "confidence_delta": round(self.confidence_delta, 4),
            "provenance_differences": list(self.provenance_differences),
        }


@dataclass
class SearchResult:
    """Ranked search result item."""

    skill_id: str
    canonical_name: str
    description: str
    current_version: Optional[str]
    status: SkillStatus
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "current_version": self.current_version,
            "status": self.status.value,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
        }


@dataclass
class DuplicateMatch:
    """Detected candidate duplicate skill or version."""

    skill_id_a: str
    version_a: str
    skill_id_b: str
    version_b: str
    similarity_score: float
    match_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id_a": self.skill_id_a,
            "version_a": self.version_a,
            "skill_id_b": self.skill_id_b,
            "version_b": self.version_b,
            "similarity_score": round(self.similarity_score, 4),
            "match_reasons": list(self.match_reasons),
        }


@dataclass
class VariantMatch:
    """Detected variant pathway for a skill."""

    skill_id: str
    version_a: str
    version_b: str
    common_goal: str
    differing_pathway: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version_a": self.version_a,
            "version_b": self.version_b,
            "common_goal": self.common_goal,
            "differing_pathway": self.differing_pathway,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ConflictMatch:
    """Detected semantic conflict."""

    skill_id: str
    version_a: str
    version_b: str
    conflict_type: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version_a": self.version_a,
            "version_b": self.version_b,
            "conflict_type": self.conflict_type,
            "description": self.description,
        }
