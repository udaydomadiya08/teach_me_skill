"""Execution record ingestion, outcome analysis, performance metric aggregation, and drift detection."""

from __future__ import annotations

import collections
import statistics
from typing import Any, Optional

from teach_a_skill.learning.models import (
    ExecutionRecord,
    PerformanceMetrics,
    SkillPerformanceProfile,
)


class OutcomeAnalyzer:
    """Evaluates individual execution outcomes and correlates verification with recovery."""

    @classmethod
    def analyze_record(cls, record: ExecutionRecord) -> dict[str, Any]:
        """Produce structured analytical summary from execution record."""
        is_success = record.final_outcome in ("SUCCESS", "RECOVERED")
        is_verified = (
            is_success
            and bool(record.verification_results)
            and all(v.get("passed", False) for v in record.verification_results)
        )
        return {
            "execution_id": record.execution_id,
            "skill_id": record.skill_id,
            "version": record.skill_version,
            "is_success": is_success,
            "is_verified": is_verified,
            "recovered": record.recovery_successes > 0,
            "duration": record.execution_duration,
            "failures": record.failure_types,
            "intervened": record.user_intervention,
        }


class PerformanceTracker:
    """Aggregates execution metrics, generates skill performance profiles, and detects regressions."""

    def __init__(self) -> None:
        self._records_by_skill: dict[str, list[ExecutionRecord]] = collections.defaultdict(list)

    def record_execution(self, record: ExecutionRecord) -> None:
        """Ingest a new execution record."""
        self._records_by_skill[record.skill_id].append(record)

    def get_records(self, skill_id: str) -> list[ExecutionRecord]:
        return list(self._records_by_skill.get(skill_id, []))

    def compute_metrics(self, skill_id: str, version: Optional[str] = None) -> PerformanceMetrics:
        """Compute aggregated metrics across executions for a skill (and optional version)."""
        records = self._records_by_skill.get(skill_id, [])
        if version:
            records = [r for r in records if r.skill_version == version]

        total = len(records)
        if total == 0:
            return PerformanceMetrics()

        successes = sum(1 for r in records if r.final_outcome in ("SUCCESS", "RECOVERED"))
        verified = sum(
            1 for r in records
            if r.final_outcome in ("SUCCESS", "RECOVERED")
            and (not r.verification_results or all(v.get("passed", False) for v in r.verification_results))
        )
        failures = sum(1 for r in records if r.final_outcome == "FAILED")
        recoveries = sum(1 for r in records if r.recovery_successes > 0)
        interventions = sum(1 for r in records if r.user_intervention)
        retries = sum(1 for r in records if r.recovery_attempts > 0)

        durations = [r.execution_duration for r in records]
        mean_time = round(statistics.mean(durations), 3) if durations else 0.0
        median_time = round(statistics.median(durations), 3) if durations else 0.0

        if len(durations) >= 5:
            sorted_durations = sorted(durations)
            p95_idx = int(len(sorted_durations) * 0.95)
            p95_time = round(sorted_durations[p95_idx], 3)
        else:
            p95_time = max(durations) if durations else 0.0

        grounding_conf_sum = sum(r.grounding_confidence for r in records)
        grounding_success_rate = round(grounding_conf_sum / total, 3)

        postcond_successes = sum(
            1 for r in records
            if r.verification_results and all(v.get("passed", False) for v in r.verification_results)
        )
        postcond_rate = round(postcond_successes / total, 3) if postcond_successes else round(successes / total, 3)

        return PerformanceMetrics(
            sample_count=total,
            success_rate=round(successes / total, 3),
            verified_success_rate=round(verified / total, 3),
            failure_rate=round(failures / total, 3),
            recovery_rate=round(recoveries / total, 3),
            mean_execution_time=mean_time,
            median_execution_time=median_time,
            p95_execution_time=p95_time,
            grounding_success_rate=grounding_success_rate,
            postcondition_success_rate=postcond_rate,
            manual_intervention_rate=round(interventions / total, 3),
            retry_rate=round(retries / total, 3),
            rollback_rate=0.0,
        )

    def get_performance_profile(self, skill_id: str, version: str) -> SkillPerformanceProfile:
        """Construct full statistical performance profile for a skill version."""
        records = [r for r in self._records_by_skill.get(skill_id, []) if r.skill_version == version]
        metrics = self.compute_metrics(skill_id, version)

        failure_dist: dict[str, int] = collections.defaultdict(int)
        recovery_dist: dict[str, int] = collections.defaultdict(int)
        env_dist: dict[str, int] = collections.defaultdict(int)
        hw_dist: dict[str, int] = collections.defaultdict(int)
        conf_dist: dict[str, int] = collections.defaultdict(int)

        for r in records:
            for f in r.failure_types:
                failure_dist[f] += 1
            if r.recovery_attempts > 0:
                recovery_dist["attempts"] += r.recovery_attempts
                recovery_dist["successes"] += r.recovery_successes
            env_dist[r.environment_signature] += 1
            tier = r.hardware_profile.get("tier", "BASELINE")
            hw_dist[tier] += 1
            bucket = f"{int(r.grounding_confidence * 10) * 10}%"
            conf_dist[bucket] += 1

        # Determine trend
        trend = "STABLE"
        if len(records) >= 6:
            half = len(records) // 2
            first_half_success = sum(1 for r in records[:half] if r.final_outcome in ("SUCCESS", "RECOVERED")) / half
            second_half_success = sum(1 for r in records[half:] if r.final_outcome in ("SUCCESS", "RECOVERED")) / (len(records) - half)
            if second_half_success < first_half_success - 0.15:
                trend = "DEGRADING"
            elif second_half_success > first_half_success + 0.15:
                trend = "IMPROVING"

        fingerprint = f"{skill_id}:{version}:{len(records)}:{metrics.success_rate}"

        return SkillPerformanceProfile(
            skill_id=skill_id,
            version=version,
            sample_count=len(records),
            metrics=metrics,
            failure_distribution=dict(failure_dist),
            recovery_distribution=dict(recovery_dist),
            environment_distribution=dict(env_dist),
            hardware_distribution=dict(hw_dist),
            confidence_distribution=dict(conf_dist),
            performance_trend=trend,
            fingerprint=fingerprint,
        )

    def check_skill_drift(self, skill_id: str, version: str) -> tuple[bool, str]:
        """Detect environment shifts or drift: declining grounding confidence or spiking failures."""
        records = [r for r in self._records_by_skill.get(skill_id, []) if r.skill_version == version]
        if len(records) < 4:
            return False, "Insufficient execution records to evaluate drift"

        recent = records[-3:]
        recent_failures = sum(1 for r in recent if r.final_outcome == "FAILED")
        recent_avg_conf = sum(r.grounding_confidence for r in recent) / 3.0

        if recent_failures >= 2 or recent_avg_conf < 0.60:
            return True, f"SKILL_DRIFT_DETECTED: {recent_failures}/3 recent failures, grounding confidence at {recent_avg_conf:.2f}"

        return False, "Skill performance within normal confidence parameters"
