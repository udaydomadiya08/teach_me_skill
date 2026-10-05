"""Recovery grounder for Phase 11.

Performs fresh environment re-observation and semantic re-grounding
when targets move, rename, or transiently disappear.
Strictly prevents the reuse of stale coordinates or ambiguous UI references.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from teach_a_skill.execution.environment import LocalEnvironmentAdapter
from teach_a_skill.execution.grounding import SemanticGrounder
from teach_a_skill.execution.models import (
    EnvironmentElement,
    EnvironmentSnapshot,
    GroundingCandidate,
    GroundingMatchType,
    GroundingResult,
)
from teach_a_skill.recovery.models import (
    BoundingBox,
    FailureRecord,
    FailureType,
    RecoveryPolicy,
    UIElementObservation,
)
from teach_a_skill.skill.models import SkillStep

logger = logging.getLogger(__name__)


@dataclass
class RegroundingEvidence:
    """Detailed audit record of a re-grounding operation."""

    step_id: str
    old_target: str
    new_target: Optional[str]
    why_regrounding_occurred: str
    old_coordinates: Optional[BoundingBox]
    new_coordinates: Optional[BoundingBox]
    new_confidence: float
    ambiguity_margin: float
    candidate_count: int
    evidence: dict[str, Any] = field(default_factory=dict)
    regrounded: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "old_target": self.old_target,
            "new_target": self.new_target,
            "why_regrounding_occurred": self.why_regrounding_occurred,
            "old_coordinates": self.old_coordinates.to_dict() if self.old_coordinates else None,
            "new_coordinates": self.new_coordinates.to_dict() if self.new_coordinates else None,
            "new_confidence": round(self.new_confidence, 4),
            "ambiguity_margin": round(self.ambiguity_margin, 4),
            "candidate_count": self.candidate_count,
            "evidence": self.evidence,
            "regrounded": self.regrounded,
            "timestamp": self.timestamp,
        }


class RecoveryGrounder:
    """Executes fresh re-observation and bounded semantic re-grounding."""

    def __init__(
        self,
        environment_adapter: LocalEnvironmentAdapter,
        base_grounder: Optional[SemanticGrounder] = None,
        policy: Optional[RecoveryPolicy] = None,
    ) -> None:
        self.adapter = environment_adapter
        self.grounder = base_grounder or SemanticGrounder()
        self.policy = policy or RecoveryPolicy()

    def reobserve_and_reground(
        self,
        step: SkillStep,
        failure: FailureRecord,
        old_grounding: Optional[GroundingResult] = None,
    ) -> tuple[Optional[GroundingResult], RegroundingEvidence]:
        """Perform a fresh observation cycle and re-ground the target element.

        Never reuses stale coordinates or stale UI snapshots.
        """
        old_target = step.target_element or "unspecified_target"
        old_bbox = (
            BoundingBox(
                x=old_grounding.best_candidate.pixel_x,
                y=old_grounding.best_candidate.pixel_y,
                width=old_grounding.best_candidate.pixel_width,
                height=old_grounding.best_candidate.pixel_height,
            )
            if old_grounding and old_grounding.best_candidate
            else None
        )

        # 1. Fresh observation
        fresh_snapshot = self.adapter.observe()

        # 2. Check Application Compatibility
        expected_app = step.parameters.get("expected_application") or step.parameters.get("app_name")
        if expected_app and fresh_snapshot.active_application:
            if expected_app.lower() not in fresh_snapshot.active_application.lower():
                evidence = RegroundingEvidence(
                    step_id=step.step_id,
                    old_target=old_target,
                    new_target=None,
                    why_regrounding_occurred="Active application mismatch during re-observation",
                    old_coordinates=old_bbox,
                    new_coordinates=None,
                    new_confidence=0.0,
                    ambiguity_margin=0.0,
                    candidate_count=0,
                    evidence={
                        "expected_app": expected_app,
                        "actual_app": fresh_snapshot.active_application,
                    },
                    regrounded=False,
                )
                return None, evidence

        # 3. Try base grounding against fresh snapshot
        fresh_grounding = self.grounder.ground_step(step, fresh_snapshot)

        if fresh_grounding.grounded and fresh_grounding.confidence >= self.policy.minimum_recovery_confidence:
            best = fresh_grounding.best_candidate
            new_bbox = (
                BoundingBox(
                    x=best.pixel_x,
                    y=best.pixel_y,
                    width=best.pixel_width,
                    height=best.pixel_height,
                )
                if best
                else None
            )

            margin = 1.0
            if len(fresh_grounding.all_candidates) > 1:
                sorted_cands = sorted(fresh_grounding.all_candidates, key=lambda c: c.confidence, reverse=True)
                margin = sorted_cands[0].confidence - sorted_cands[1].confidence

            reason = "Fresh grounding successful against updated environment"
            if old_bbox and new_bbox:
                if (old_bbox.x, old_bbox.y) != (new_bbox.x, new_bbox.y):
                    reason = f"Target moved: coordinates shifted from ({old_bbox.x},{old_bbox.y}) to ({new_bbox.x},{new_bbox.y})"

            new_target_label = (
                best.accessibility_label or best.target_name if best else old_target
            )
            evidence = RegroundingEvidence(
                step_id=step.step_id,
                old_target=old_target,
                new_target=new_target_label,
                why_regrounding_occurred=reason,
                old_coordinates=old_bbox,
                new_coordinates=new_bbox,
                new_confidence=fresh_grounding.confidence,
                ambiguity_margin=margin,
                candidate_count=len(fresh_grounding.all_candidates),
                evidence={
                    "strategy": "direct_fresh_grounding",
                    "matched_role": best.element_role if best else None,
                },
                regrounded=True,
            )
            return fresh_grounding, evidence

        # 4. Fallback: Fuzzy / Semantic Renaming search on UI elements
        best_candidate: Optional[EnvironmentElement] = None
        best_cand_score = 0.0
        expected_role = step.parameters.get("role") or step.parameters.get("element_type")

        for elem in fresh_snapshot.elements:
            elem_text = elem.label or elem.title or elem.value or ""
            if not elem_text:
                continue

            # Role compatibility check
            if expected_role and elem.role:
                if expected_role.lower() not in elem.role.lower() and elem.role.lower() not in expected_role.lower():
                    continue

            # Semantic string similarity
            sim = difflib.SequenceMatcher(None, old_target.lower(), elem_text.lower()).ratio()

            if old_target.lower() in elem_text.lower() or elem_text.lower() in old_target.lower():
                sim = max(sim, 0.8)

            if sim > best_cand_score:
                best_cand_score = sim
                best_candidate = elem

        if best_candidate and best_cand_score >= self.policy.minimum_recovery_confidence:
            new_target_name = best_candidate.label or best_candidate.title or old_target
            new_bbox = BoundingBox(
                x=best_candidate.pixel_x,
                y=best_candidate.pixel_y,
                width=best_candidate.pixel_width,
                height=best_candidate.pixel_height,
            )
            cand = GroundingCandidate(
                candidate_id=f"reground_{best_candidate.element_id}",
                target_name=new_target_name,
                match_type=GroundingMatchType.ACCESSIBILITY,
                confidence=best_cand_score,
                pixel_x=best_candidate.pixel_x,
                pixel_y=best_candidate.pixel_y,
                pixel_width=best_candidate.pixel_width,
                pixel_height=best_candidate.pixel_height,
                element_role=best_candidate.role,
                application=fresh_snapshot.active_application,
                accessibility_label=best_candidate.label or best_candidate.title,
            )
            regrounded_result = GroundingResult(
                step_id=step.step_id,
                target_name=new_target_name,
                grounded=True,
                confidence=best_cand_score,
                best_candidate=cand,
                all_candidates=[cand],
                ambiguous=False,
                explanation="Recovery grounder matched renamed or relocated element",
            )

            evidence = RegroundingEvidence(
                step_id=step.step_id,
                old_target=old_target,
                new_target=new_target_name,
                why_regrounding_occurred=f"Semantic target renamed or matched fuzzy text '{new_target_name}' (similarity={best_cand_score:.2f})",
                old_coordinates=old_bbox,
                new_coordinates=new_bbox,
                new_confidence=best_cand_score,
                ambiguity_margin=0.5,
                candidate_count=1,
                evidence={
                    "semantic_similarity": best_cand_score,
                    "element_role": best_candidate.role,
                },
                regrounded=True,
            )
            return regrounded_result, evidence

        # Failed re-grounding: Target genuinely disappeared or remains ambiguous
        evidence = RegroundingEvidence(
            step_id=step.step_id,
            old_target=old_target,
            new_target=None,
            why_regrounding_occurred="Target element not found in live environment after re-observation",
            old_coordinates=old_bbox,
            new_coordinates=None,
            new_confidence=0.0,
            ambiguity_margin=0.0,
            candidate_count=len(fresh_snapshot.elements),
            evidence={"fresh_elements_examined": len(fresh_snapshot.elements)},
            regrounded=False,
        )
        return None, evidence
