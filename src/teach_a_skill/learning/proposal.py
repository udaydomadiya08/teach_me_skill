"""Evidence-backed improvement proposal generation with loop protection and safety boundaries."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Optional

from teach_a_skill.learning.models import (
    EnvironmentVariation,
    FailurePattern,
    ImprovementProposal,
    VariationType,
)


class ImprovementGenerator:
    """Generates bounded, evidence-driven skill improvement proposals."""

    FORBIDDEN_KEYWORDS = [
        "rm -rf",
        "sudo",
        "eval(",
        "exec(",
        "password",
        "credential",
        "grant_permission",
        "bypass_safety",
        "chmod",
        "subprocess",
    ]

    def __init__(self) -> None:
        self._seen_fingerprints: set[str] = set()

    def generate_proposals(
        self,
        skill_id: str,
        base_version: str,
        patterns: list[FailurePattern],
        variations: Optional[list[EnvironmentVariation]] = None,
    ) -> list[ImprovementProposal]:
        """Formulate bounded proposals based strictly on detected patterns and variations."""
        proposals: list[ImprovementProposal] = []
        variations = variations or []

        # 1. Proposals from failure patterns
        for pat in patterns:
            prop = None
            if "RENAME" in pat.pattern_type or "LABEL" in pat.pattern_type or "TARGET_NOT_FOUND" in pat.pattern_type:
                prop = ImprovementProposal(
                    proposal_id=f"prop-{uuid.uuid4().hex[:10]}",
                    skill_id=skill_id,
                    base_version=base_version,
                    reason=f"Recurring failure '{pat.pattern_type}' on step '{pat.affected_step}'. Add grounding label alias.",
                    evidence_refs=pat.evidence_refs,
                    affected_steps=[pat.affected_step],
                    proposed_change={
                        "type": "add_grounding_alias",
                        "step_id": pat.affected_step,
                        "alias": f"alias_for_{pat.affected_step}",
                    },
                    expected_benefit="Enhances semantic grounding robustness across UI variations",
                    risk="LOW",
                    confidence=pat.confidence,
                    required_validation=["shadow_eval", "grounding_check"],
                )
            elif "TIMEOUT" in pat.pattern_type:
                prop = ImprovementProposal(
                    proposal_id=f"prop-{uuid.uuid4().hex[:10]}",
                    skill_id=skill_id,
                    base_version=base_version,
                    reason=f"Frequent timeout on step '{pat.affected_step}'. Increase wait condition threshold.",
                    evidence_refs=pat.evidence_refs,
                    affected_steps=[pat.affected_step],
                    proposed_change={
                        "type": "adjust_timeout",
                        "step_id": pat.affected_step,
                        "timeout_multiplier": 1.5,
                    },
                    expected_benefit="Reduces transient timeouts during slow rendering",
                    risk="LOW",
                    confidence=pat.confidence,
                    required_validation=["shadow_eval"],
                )
            elif pat.common_recovery_strategy:
                prop = ImprovementProposal(
                    proposal_id=f"prop-{uuid.uuid4().hex[:10]}",
                    skill_id=skill_id,
                    base_version=base_version,
                    reason=f"Recovery strategy '{pat.common_recovery_strategy}' repeatedly succeeded for step '{pat.affected_step}'. Encode as proactive fallback.",
                    evidence_refs=pat.evidence_refs,
                    affected_steps=[pat.affected_step],
                    proposed_change={
                        "type": "add_recovery_strategy",
                        "step_id": pat.affected_step,
                        "preferred_strategy": pat.common_recovery_strategy,
                    },
                    expected_benefit=f"Encodes proven recovery heuristic '{pat.common_recovery_strategy}'",
                    risk="LOW",
                    confidence=pat.confidence,
                    required_validation=["shadow_eval", "recovery_policy_check"],
                )

            if prop:
                self._add_if_safe_and_novel(prop, proposals)

        # 2. Proposals from environment variations
        for var in variations:
            if var.variation_type == VariationType.SEMANTICALLY_EQUIVALENT_CHANGE:
                prop = ImprovementProposal(
                    proposal_id=f"prop-{uuid.uuid4().hex[:10]}",
                    skill_id=skill_id,
                    base_version=base_version,
                    reason=f"Observed semantically equivalent label variation: '{var.base_value}' -> '{var.observed_value}'.",
                    evidence_refs=var.evidence_refs,
                    affected_steps=[],
                    proposed_change={
                        "type": "add_semantic_label_alias",
                        "attribute": var.attribute_changed,
                        "canonical": var.base_value,
                        "alias": var.observed_value,
                    },
                    expected_benefit="Maintains grounding accuracy across UI wording revisions",
                    risk="LOW",
                    confidence=0.88,
                    required_validation=["shadow_eval"],
                )
                self._add_if_safe_and_novel(prop, proposals)

        return proposals

    def _add_if_safe_and_novel(
        self,
        prop: ImprovementProposal,
        proposals_list: list[ImprovementProposal],
    ) -> bool:
        """Validate safety constraints and deduplicate using deterministic fingerprinting."""
        # Safety Check: Anti-self-modification & injection defense
        change_str = str(prop.proposed_change).lower()
        reason_str = prop.reason.lower()
        for kw in self.FORBIDDEN_KEYWORDS:
            if kw in change_str or kw in reason_str:
                return False

        # Proposal loop protection: deduplicate identical proposals
        fp = prop.compute_fingerprint()
        if fp in self._seen_fingerprints:
            return False

        self._seen_fingerprints.add(fp)
        # Recreate prop with populated fingerprint
        final_prop = ImprovementProposal(
            proposal_id=prop.proposal_id,
            skill_id=prop.skill_id,
            base_version=prop.base_version,
            reason=prop.reason,
            evidence_refs=prop.evidence_refs,
            affected_steps=prop.affected_steps,
            proposed_change=prop.proposed_change,
            expected_benefit=prop.expected_benefit,
            risk=prop.risk,
            confidence=prop.confidence,
            required_validation=prop.required_validation,
            status=prop.status,
            created_at=prop.created_at,
            fingerprint=fp,
        )
        proposals_list.append(final_prop)
        return True
