"""Phase 11: Verification, Recovery & Error Handling for Teach A Skill."""

from __future__ import annotations

from teach_a_skill.recovery.benchmark import RecoveryBenchmark
from teach_a_skill.recovery.classifier import FailureClassifier, classify_action_idempotency
from teach_a_skill.recovery.engine import ResilientExecutionEngine
from teach_a_skill.recovery.grounder import RecoveryGrounder, RegroundingEvidence
from teach_a_skill.recovery.models import (
    ActionIdempotency,
    ExecutionOutcome,
    FailureRecord,
    FailureSeverity,
    FailureType,
    Recoverability,
    RecoveryAttempt,
    RecoveryBudget,
    RecoveryPlan,
    RecoveryPolicy,
    RecoveryStrategy,
    VerificationResult,
    compute_failure_fingerprint,
)
from teach_a_skill.recovery.planner import RecoveryPlanner
from teach_a_skill.recovery.storage import RecoveryStorage
from teach_a_skill.recovery.validator import RecoveryValidator
from teach_a_skill.recovery.verification import VerificationEngine

__all__ = [
    "ActionIdempotency",
    "ExecutionOutcome",
    "FailureClassifier",
    "FailureRecord",
    "FailureSeverity",
    "FailureType",
    "Recoverability",
    "RecoveryAttempt",
    "RecoveryBenchmark",
    "RecoveryBudget",
    "RecoveryEngine",
    "RecoveryGrounder",
    "RecoveryPlan",
    "RecoveryPlanner",
    "RecoveryPolicy",
    "RecoveryStorage",
    "RecoveryStrategy",
    "RecoveryValidator",
    "RegroundingEvidence",
    "ResilientExecutionEngine",
    "VerificationEngine",
    "VerificationResult",
    "classify_action_idempotency",
    "compute_failure_fingerprint",
]
