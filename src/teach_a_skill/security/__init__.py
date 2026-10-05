"""Security, hardening, permission management, audit integrity, and supply-chain verification."""

from __future__ import annotations

from teach_a_skill.security.audit import (
    AuditIntegrityManager,
    ChainedAuditRecord,
    SecurityIncidentError,
)
from teach_a_skill.security.benchmark import (
    Phase14BenchmarkResults,
    Phase14BenchmarkRunner,
)
from teach_a_skill.security.dependencies import (
    DependencyAuditor,
    DependencyRecord,
)
from teach_a_skill.security.filesystem import (
    DeletionMode,
    DeletionReport,
    SecurityViolationError,
    StorageSecurityManager,
)
from teach_a_skill.security.network import (
    NetworkIsolationMonitor,
    NetworkIsolationViolationError,
)
from teach_a_skill.security.permissions import (
    PermissionDeniedError,
    PermissionManager,
    PermissionState,
    PermissionType,
)
from teach_a_skill.security.retention import (
    RetentionManager,
    RetentionPolicy,
)
from teach_a_skill.security.secrets import (
    SecretDetector,
    SecretMatch,
)

__all__ = [
    "PermissionManager",
    "PermissionType",
    "PermissionState",
    "PermissionDeniedError",
    "SecretDetector",
    "SecretMatch",
    "StorageSecurityManager",
    "SecurityViolationError",
    "DeletionMode",
    "DeletionReport",
    "AuditIntegrityManager",
    "ChainedAuditRecord",
    "SecurityIncidentError",
    "RetentionPolicy",
    "RetentionManager",
    "DependencyAuditor",
    "DependencyRecord",
    "NetworkIsolationMonitor",
    "NetworkIsolationViolationError",
    "Phase14BenchmarkResults",
    "Phase14BenchmarkRunner",
]
