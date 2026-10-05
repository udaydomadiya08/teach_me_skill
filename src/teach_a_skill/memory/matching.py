"""Semantic matching, duplicate detection, variant detection, and conflict detection.

Deterministically analyzes similarity between skill versions without requiring an LLM.
"""

from __future__ import annotations

import difflib
from typing import Any

from teach_a_skill.memory.models import (
    ConflictMatch,
    DuplicateMatch,
    VariantMatch,
)
from teach_a_skill.skill.models import SkillIR


class SkillMatcher:
    """Computes similarity and identifies duplicates, variants, and conflicts."""

    @staticmethod
    def compute_similarity(ir_a: SkillIR, ir_b: SkillIR) -> tuple[float, list[str]]:
        """Compute semantic similarity score (0.0 to 1.0) and matching features."""
        matches: list[str] = []
        total_weight = 0.0
        weighted_score = 0.0

        # 1. Intent match (weight = 20)
        total_weight += 20.0
        if ir_a.intent_type == ir_b.intent_type:
            weighted_score += 20.0
            matches.append(f"Identical intent: '{ir_a.intent_type}'")

        # 2. Goal text similarity (weight = 30)
        total_weight += 30.0
        ratio = difflib.SequenceMatcher(
            None, ir_a.goal.lower().strip(), ir_b.goal.lower().strip()
        ).ratio()
        weighted_score += 30.0 * ratio
        if ratio >= 0.8:
            matches.append(f"Highly aligned goal ({int(ratio * 100)}% text similarity)")

        # 3. Action sequence similarity (weight = 30)
        total_weight += 30.0
        actions_a = [s.action_type.value for s in ir_a.steps]
        actions_b = [s.action_type.value for s in ir_b.steps]
        seq_ratio = difflib.SequenceMatcher(None, actions_a, actions_b).ratio()
        weighted_score += 30.0 * seq_ratio
        if seq_ratio >= 0.8:
            matches.append(f"Matching semantic action sequence ({int(seq_ratio * 100)}%)")

        # 4. Target / Entity overlap (weight = 20)
        total_weight += 20.0
        targets_a = {s.target for s in ir_a.steps if s.target}
        targets_b = {s.target for s in ir_b.steps if s.target}
        if targets_a and targets_b:
            overlap = len(targets_a & targets_b) / len(targets_a | targets_b)
            weighted_score += 20.0 * overlap
            if overlap >= 0.7:
                matches.append(f"High entity/target overlap ({int(overlap * 100)}%)")
        elif not targets_a and not targets_b:
            weighted_score += 20.0

        final_score = weighted_score / total_weight if total_weight > 0 else 0.0
        return round(final_score, 4), matches

    @classmethod
    def detect_duplicate(
        cls,
        skill_id_a: str,
        version_a: str,
        ir_a: SkillIR,
        skill_id_b: str,
        version_b: str,
        ir_b: SkillIR,
        threshold: float = 0.85,
    ) -> DuplicateMatch | None:
        """Detect if two skills or versions represent candidate duplicates."""
        score, matches = cls.compute_similarity(ir_a, ir_b)
        if score >= threshold:
            return DuplicateMatch(
                skill_id_a=skill_id_a,
                version_a=version_a,
                skill_id_b=skill_id_b,
                version_b=version_b,
                similarity_score=score,
                match_reasons=matches,
            )
        return None

    @classmethod
    def detect_variant(
        cls,
        skill_id: str,
        version_a: str,
        ir_a: SkillIR,
        version_b: str,
        ir_b: SkillIR,
    ) -> VariantMatch | None:
        """Detect if two versions share a common goal via different action pathways."""
        goal_ratio = difflib.SequenceMatcher(
            None, ir_a.goal.lower().strip(), ir_b.goal.lower().strip()
        ).ratio()

        if goal_ratio < 0.75:
            return None

        # Check action pathway differences
        actions_a = [s.action_type.value for s in ir_a.steps]
        actions_b = [s.action_type.value for s in ir_b.steps]
        seq_ratio = difflib.SequenceMatcher(None, actions_a, actions_b).ratio()

        # If goal is identical/similar but action sequence differs significantly
        if seq_ratio < 0.8:
            differing = (
                f"Version {version_a} uses [{', '.join(actions_a[:3])}...] "
                f"while Version {version_b} uses [{', '.join(actions_b[:3])}...]"
            )
            return VariantMatch(
                skill_id=skill_id,
                version_a=version_a,
                version_b=version_b,
                common_goal=ir_a.goal,
                differing_pathway=differing,
                confidence=round(goal_ratio, 4),
            )
        return None

    @classmethod
    def detect_conflict(
        cls,
        skill_id: str,
        version_a: str,
        ir_a: SkillIR,
        version_b: str,
        ir_b: SkillIR,
    ) -> ConflictMatch | None:
        """Detect if two versions under the same skill identity have contradictory goals."""
        goal_a = ir_a.goal.lower()
        goal_b = ir_b.goal.lower()

        contradictions = [
            ("save", "delete"),
            ("create", "delete"),
            ("open", "close"),
            ("enable", "disable"),
            ("install", "uninstall"),
        ]
        for w1, w2 in contradictions:
            if (w1 in goal_a and w2 in goal_b) or (w2 in goal_a and w1 in goal_b):
                return ConflictMatch(
                    skill_id=skill_id,
                    version_a=version_a,
                    version_b=version_b,
                    conflict_type="CONTRADICTORY_GOALS",
                    description=f"Contradictory semantic goals: '{ir_a.goal}' vs '{ir_b.goal}'",
                )

        # Mutually exclusive postconditions
        post_a = {getattr(p, "postcondition_type", getattr(p, "type", "")) for p in ir_a.postconditions}
        post_b = {getattr(p, "postcondition_type", getattr(p, "type", "")) for p in ir_b.postconditions}
        if "FILE_SAVED" in post_a and "FILE_DELETED" in post_b:
            return ConflictMatch(
                skill_id=skill_id,
                version_a=version_a,
                version_b=version_b,
                conflict_type="INCOMPATIBLE_POSTCONDITIONS",
                description="Mutually exclusive postconditions FILE_SAVED and FILE_DELETED.",
            )

        return None
