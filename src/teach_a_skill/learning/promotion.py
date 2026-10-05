"""Promotion policy gate enforcement, candidate promotion, and deterministic rollback."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from teach_a_skill.core.errors import TeachSkillError
from teach_a_skill.learning.models import (
    CandidateSkillVersion,
    LearningAudit,
    PromotionMode,
    PromotionPolicy,
)


class PromotionPolicyViolationError(TeachSkillError):
    """Raised when candidate promotion violates safety or evidence thresholds."""
    pass


class PromotionManager:
    """Evaluates promotion criteria and promotes validated candidate SkillVersions."""

    def __init__(self, policy: Optional[PromotionPolicy] = None) -> None:
        self.policy = policy or PromotionPolicy()
        self._promotion_history: list[dict[str, Any]] = []

    def evaluate_promotion(
        self,
        candidate: CandidateSkillVersion,
        comparison: dict[str, Any],
        operator_approved: bool = False,
    ) -> tuple[bool, str]:
        """Evaluate candidate against explicit promotion policy thresholds."""
        # 1. Mode check
        if self.policy.mode == PromotionMode.MANUAL_ONLY and not operator_approved:
            return False, "Promotion policy requires explicit manual approval (mode: MANUAL_ONLY)"

        # 2. Evidence sample count check
        sample_size = comparison.get("shadow_sample_count", 0)
        if sample_size < self.policy.minimum_executions:
            return False, f"Insufficient sample size ({sample_size} < {self.policy.minimum_executions})"

        # 3. Regression check
        if comparison.get("regression_detected", False):
            return False, "Critical regression detected during shadow evaluation"

        # 4. Improvement check
        delta = comparison.get("success_rate_delta", 0.0)
        if delta < self.policy.minimum_success_improvement and not comparison.get("is_improved", False):
            return False, f"Projected improvement ({delta}) is below threshold ({self.policy.minimum_success_improvement})"

        # 5. High-risk change validation
        diff = candidate.diff
        if diff.get("recovery_changed", False) and self.policy.mode != PromotionMode.AUTOMATIC_SAFE and not operator_approved:
            return False, "Recovery modifications require supervised operator approval"

        return True, "All promotion policy thresholds and safety gates satisfied"

    def promote_candidate(
        self,
        candidate: CandidateSkillVersion,
        comparison: dict[str, Any],
        operator_approved: bool = False,
    ) -> CandidateSkillVersion:
        """Promote candidate to active version if gate evaluation passes."""
        can_promote, reason = self.evaluate_promotion(candidate, comparison, operator_approved)
        if not can_promote:
            raise PromotionPolicyViolationError(f"Candidate promotion rejected: {reason}")

        promoted_candidate = CandidateSkillVersion(
            candidate_id=candidate.candidate_id,
            skill_id=candidate.skill_id,
            base_version=candidate.base_version,
            candidate_version=candidate.candidate_version,
            fingerprint=candidate.fingerprint,
            diff=candidate.diff,
            reason=candidate.reason,
            evidence_refs=candidate.evidence_refs,
            skill_ir=candidate.skill_ir,
            validation_results={**candidate.validation_results, "promoted": True},
            created_at=candidate.created_at,
            is_promoted=True,
        )

        record = {
            "skill_id": candidate.skill_id,
            "previous_version": candidate.base_version,
            "promoted_version": candidate.candidate_version,
            "fingerprint": candidate.fingerprint,
            "reason": candidate.reason,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._promotion_history.append(record)
        return promoted_candidate

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._promotion_history)


class RollbackManager:
    """Manages safe rollback of promoted skill versions upon regression detection."""

    def __init__(self) -> None:
        self._rollback_events: list[dict[str, Any]] = []

    def rollback(
        self,
        skill_id: str,
        current_version: str,
        target_version: str,
        reason: str,
    ) -> dict[str, Any]:
        """Perform rollback to designated previous stable SkillVersion."""
        event = {
            "skill_id": skill_id,
            "rolled_back_from": current_version,
            "restored_version": target_version,
            "reason": reason,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._rollback_events.append(event)
        return event

    def list_rollbacks(self) -> list[dict[str, Any]]:
        return list(self._rollback_events)
