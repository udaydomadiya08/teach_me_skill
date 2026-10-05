"""Deterministic failure pattern detection and environmental variation classification."""

from __future__ import annotations

import collections
import hashlib
from typing import Any, Optional

from teach_a_skill.learning.models import (
    EnvironmentVariation,
    ExecutionRecord,
    FailurePattern,
    VariationType,
)


class FailurePatternDetector:
    """Discovers recurring execution failure modes subject to minimum evidence thresholds."""

    def __init__(
        self,
        min_frequency: int = 2,
        min_sample_size: int = 3,
    ) -> None:
        self.min_frequency = min_frequency
        self.min_sample_size = min_sample_size

    def detect_patterns(
        self,
        skill_id: str,
        records: list[ExecutionRecord],
    ) -> list[FailurePattern]:
        """Group failures by fingerprint and identify recurring patterns."""
        if len(records) < self.min_sample_size:
            return []

        # Map: (failure_type, affected_step) -> list of records
        failure_clusters: dict[tuple[str, str], list[ExecutionRecord]] = collections.defaultdict(list)

        for rec in records:
            if rec.final_outcome in ("FAILED", "RECOVERED") and rec.failure_types:
                for f_type in rec.failure_types:
                    step = "step_unknown"
                    for v in rec.verification_results:
                        if not v.get("passed", False):
                            step = v.get("step_id", step)
                            break
                    failure_clusters[(f_type, step)].append(rec)

        detected_patterns: list[FailurePattern] = []
        for (f_type, step), cluster in failure_clusters.items():
            freq = len(cluster)
            if freq >= self.min_frequency:
                # Find common successful recovery strategy if any
                recoveries = [r.provenance.get("recovery_strategy") for r in cluster if r.recovery_successes > 0]
                common_strat = None
                if recoveries:
                    strat_counts = collections.Counter(recoveries)
                    common_strat, _ = strat_counts.most_common(1)[0]

                env_sigs = {r.environment_signature for r in cluster}
                primary_env = list(env_sigs)[0] if len(env_sigs) == 1 else "multiple_environments"

                conf = round(min(0.99, 0.60 + (freq * 0.10)), 2)
                p_id = f"pat-{hashlib.sha256(f'{skill_id}:{f_type}:{step}'.encode()).hexdigest()[:10]}"

                detected_patterns.append(
                    FailurePattern(
                        pattern_id=p_id,
                        pattern_type=f_type,
                        skill_id=skill_id,
                        affected_step=step,
                        frequency=freq,
                        sample_count=len(records),
                        environment_signature=primary_env,
                        common_recovery_strategy=common_strat,
                        confidence=conf,
                        evidence_refs=[r.execution_id for r in cluster],
                    )
                )

        return detected_patterns


class VariationDetector:
    """Classifies host UI, geometric, and semantic label variations across executions."""

    @classmethod
    def classify_variation(
        cls,
        attribute_name: str,
        base_val: Any,
        observed_val: Any,
    ) -> VariationType:
        """Categorize variation type based on attribute characteristics."""
        b_str = str(base_val).lower().strip()
        o_str = str(observed_val).lower().strip()

        if b_str == o_str:
            return VariationType.UNKNOWN_CHANGE

        # Geometric changes
        if any(g in attribute_name.lower() for g in ("coord", "box", "pixel", "position", "x", "y", "width", "height")):
            return VariationType.GEOMETRIC_CHANGE

        # Cosmetic changes
        if any(c in attribute_name.lower() for c in ("theme", "color", "font", "style", "dark_mode")):
            return VariationType.COSMETIC_CHANGE

        # Semantic equivalence
        label_pairs = {
            ("save", "save document"),
            ("open", "open file"),
            ("cancel", "dismiss"),
            ("ok", "confirm"),
            ("submit", "send"),
        }
        if (b_str, o_str) in label_pairs or (o_str, b_str) in label_pairs:
            return VariationType.SEMANTICALLY_EQUIVALENT_CHANGE

        if b_str in o_str or o_str in b_str:
            return VariationType.SEMANTICALLY_EQUIVALENT_CHANGE

        # Full semantic change
        return VariationType.SEMANTIC_CHANGE

    @classmethod
    def detect_variations(
        cls,
        skill_id: str,
        base_environment: dict[str, Any],
        observed_environments: list[dict[str, Any]],
    ) -> list[EnvironmentVariation]:
        """Identify variations across observed execution environments."""
        variations: list[EnvironmentVariation] = []
        if not observed_environments:
            return variations

        # Aggregate attribute frequencies
        diff_counts: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))

        for env in observed_environments:
            for k, obs_v in env.items():
                base_v = base_environment.get(k)
                if base_v is not None and str(base_v) != str(obs_v):
                    diff_counts[k][str(obs_v)] += 1

        for attr, obs_map in diff_counts.items():
            base_v = base_environment.get(attr)
            for obs_v, count in obs_map.items():
                v_type = cls.classify_variation(attr, base_v, obs_v)
                impact = 0.2 if v_type == VariationType.COSMETIC_CHANGE else (
                    0.4 if v_type == VariationType.GEOMETRIC_CHANGE else (
                        0.3 if v_type == VariationType.SEMANTICALLY_EQUIVALENT_CHANGE else 0.8
                    )
                )
                v_id = f"var-{hashlib.sha256(f'{skill_id}:{attr}:{obs_v}'.encode()).hexdigest()[:10]}"
                variations.append(
                    EnvironmentVariation(
                        variation_id=v_id,
                        skill_id=skill_id,
                        variation_type=v_type,
                        attribute_changed=attr,
                        base_value=str(base_v),
                        observed_value=obs_v,
                        frequency=count,
                        impact_score=impact,
                        evidence_refs=[],
                    )
                )

        return variations
