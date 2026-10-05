"""Semantic comparator for Skill IR versions.

Generates machine-readable and human-readable diffs, and deterministically
classifies version changes into PATCH, MINOR, MAJOR, or CONFLICT.
"""

from __future__ import annotations

import logging
from typing import Optional

from teach_a_skill.memory.models import VersionBump, VersionDiff
from teach_a_skill.skill.models import SkillIR

logger = logging.getLogger(__name__)


class SkillComparator:
    """Compares two Skill IRs and recommends semantic version bumps."""

    @classmethod
    def compare(
        cls,
        skill_id: str,
        version_a_str: str,
        ir_a: SkillIR,
        version_b_str: str,
        ir_b: SkillIR,
    ) -> VersionDiff:
        """Perform deep semantic comparison between version A and version B."""
        semantic_changes: list[str] = []
        param_changes: list[str] = []
        step_changes: list[str] = []
        prec_changes: list[str] = []
        post_changes: list[str] = []
        grounding_changes: list[str] = []
        dep_changes: list[str] = []
        provenance_diffs: list[str] = []

        is_conflict = False
        is_major = False
        is_minor = False

        # 1. Goal and Intent
        if ir_a.intent_type != ir_b.intent_type:
            semantic_changes.append(
                f"Intent changed from '{ir_a.intent_type}' to '{ir_b.intent_type}'."
            )
            is_major = True

        if ir_a.goal != ir_b.goal:
            # Check for contradictory goals (e.g. save vs delete)
            goal_a_lower = ir_a.goal.lower()
            goal_b_lower = ir_b.goal.lower()
            contradictions = [
                ("save", "delete"),
                ("create", "delete"),
                ("open", "close"),
                ("enable", "disable"),
            ]
            for word1, word2 in contradictions:
                if (word1 in goal_a_lower and word2 in goal_b_lower) or (
                    word2 in goal_a_lower and word1 in goal_b_lower
                ):
                    is_conflict = True
                    semantic_changes.append(
                        f"Contradictory goals detected: '{ir_a.goal}' vs '{ir_b.goal}'."
                    )
                    break

            if not is_conflict:
                semantic_changes.append(
                    f"Goal changed from '{ir_a.goal}' to '{ir_b.goal}'."
                )
                is_major = True

        # 2. Parameters
        params_a = {p.name: p for p in ir_a.parameters}
        params_b = {p.name: p for p in ir_b.parameters}

        # Added in B
        for name, p_b in params_b.items():
            if name not in params_a:
                if p_b.required:
                    param_changes.append(f"Added required parameter '{name}' ({p_b.type.value}).")
                    is_major = True
                else:
                    param_changes.append(
                        f"Added optional parameter '{name}' ({p_b.type.value}) with default '{p_b.default}'."
                    )
                    is_minor = True
            else:
                p_a = params_a[name]
                if p_a.type != p_b.type:
                    param_changes.append(
                        f"Parameter '{name}' changed type from {p_a.type.value} to {p_b.type.value}."
                    )
                    is_major = True
                elif not p_a.required and p_b.required:
                    param_changes.append(
                        f"Parameter '{name}' became required (previously optional)."
                    )
                    is_major = True
                elif p_a.required and not p_b.required:
                    param_changes.append(
                        f"Parameter '{name}' relaxed to optional."
                    )
                    is_minor = True

        # Removed in B
        for name, p_a in params_a.items():
            if name not in params_b:
                param_changes.append(f"Removed parameter '{name}'.")
                is_major = True

        # 3. Steps
        steps_a = ir_a.steps
        steps_b = ir_b.steps

        if len(steps_a) != len(steps_b):
            step_changes.append(
                f"Step count changed from {len(steps_a)} to {len(steps_b)}."
            )
            if len(steps_b) > len(steps_a):
                # Extra steps added: could be minor or major
                is_minor = True
            else:
                # Steps removed: breaking
                is_major = True

        min_len = min(len(steps_a), len(steps_b))
        for i in range(min_len):
            s_a = steps_a[i]
            s_b = steps_b[i]
            if s_a.action_type != s_b.action_type:
                step_changes.append(
                    f"Step {i+1} action type changed: {s_a.action_type.value} -> {s_b.action_type.value}."
                )
                is_major = True
            elif s_a.target != s_b.target:
                step_changes.append(
                    f"Step {i+1} target changed: '{s_a.target}' -> '{s_b.target}'."
                )
                is_minor = True

            # Grounding differences
            if s_a.grounding and s_b.grounding:
                if s_a.grounding.preferred_strategy != s_b.grounding.preferred_strategy:
                    grounding_changes.append(
                        f"Step {i+1} preferred grounding changed: {s_a.grounding.preferred_strategy.value} -> {s_b.grounding.preferred_strategy.value}."
                    )
                    is_minor = True
                if len(s_b.grounding.fallback_strategies) > len(s_a.grounding.fallback_strategies):
                    grounding_changes.append(
                        f"Step {i+1} expanded grounding fallback strategies."
                    )
                    is_minor = True

        # 4. Preconditions
        pre_types_a = {getattr(p, "precondition_type", getattr(p, "type", "")) for p in ir_a.preconditions}
        pre_types_b = {getattr(p, "precondition_type", getattr(p, "type", "")) for p in ir_b.preconditions}
        if pre_types_b - pre_types_a:
            prec_changes.append(f"Added new required preconditions: {sorted(pre_types_b - pre_types_a)}.")
            is_major = True
        if pre_types_a - pre_types_b:
            prec_changes.append(f"Removed preconditions: {sorted(pre_types_a - pre_types_b)}.")
            is_minor = True

        # 5. Postconditions
        post_types_a = {getattr(p, "postcondition_type", getattr(p, "type", "")) for p in ir_a.postconditions}
        post_types_b = {getattr(p, "postcondition_type", getattr(p, "type", "")) for p in ir_b.postconditions}
        if post_types_a != post_types_b:
            post_changes.append(
                f"Postconditions changed from {sorted(post_types_a)} to {sorted(post_types_b)}."
            )
            is_major = True

        # 6. Dependencies
        dep_names_a = {d.name for d in ir_a.dependencies if d.required}
        dep_names_b = {d.name for d in ir_b.dependencies if d.required}
        if dep_names_b - dep_names_a:
            dep_changes.append(f"Added new required dependencies: {sorted(dep_names_b - dep_names_a)}.")
            is_major = True
        if dep_names_a - dep_names_b:
            dep_changes.append(f"Removed required dependencies: {sorted(dep_names_a - dep_names_b)}.")
            is_minor = True

        # 7. Confidence & Provenance
        confidence_delta = ir_b.confidence - ir_a.confidence
        demo_a = set(ir_a.provenance.get("source_demonstration_ids", []))
        demo_b = set(ir_b.provenance.get("source_demonstration_ids", []))
        if demo_a != demo_b:
            provenance_diffs.append(
                f"Source demonstration IDs changed: {sorted(demo_a)} -> {sorted(demo_b)}."
            )

        # Recommendation synthesis
        if is_conflict:
            recommended_bump = VersionBump.CONFLICT
            explanation = "Contradictory semantic goals or incompatible mutual exclusion detected."
        elif is_major:
            recommended_bump = VersionBump.MAJOR
            explanation = "Breaking semantic changes detected (changed goal, required parameters, core steps, preconditions, or dependencies)."
        elif is_minor:
            recommended_bump = VersionBump.MINOR
            explanation = "Backward-compatible semantic enhancements detected (optional parameters, extra targets, or expanded grounding strategies)."
        else:
            recommended_bump = VersionBump.PATCH
            explanation = "No breaking or functional semantic changes; metadata, descriptions, or internal representation adjustments only."

        return VersionDiff(
            skill_id=skill_id,
            version_a=version_a_str,
            version_b=version_b_str,
            recommended_bump=recommended_bump,
            explanation=explanation,
            semantic_changes=semantic_changes,
            parameter_changes=param_changes,
            step_changes=step_changes,
            precondition_changes=prec_changes,
            postcondition_changes=post_changes,
            grounding_changes=grounding_changes,
            dependency_changes=dep_changes,
            confidence_delta=confidence_delta,
            provenance_differences=provenance_diffs,
        )
