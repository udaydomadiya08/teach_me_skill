"""Synthetic and long-run benchmarks for Phase 11 recovery.

Measures:
1. Failure classification throughput and memory at 100, 1,000, and 10,000 failures.
2. Recovery planning latency across 10, 50, and 100 step sequences.
3. Multi-source verification performance across 10, 100, and 1,000 candidates.
4. Long-run stability and memory growth over 500 recovery cycles.
"""

from __future__ import annotations

import logging
import os
import resource
import time
from typing import Any

from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentElement,
    EnvironmentSnapshot,
    PlannedAction,
    SafetyLevel,
    StepExecutionResult,
    StepStatus,
)
from teach_a_skill.recovery.classifier import FailureClassifier
from teach_a_skill.recovery.models import (
    BoundingBox,
    FailureRecord,
    FailureType,
    RecoveryBudget,
    RecoveryPolicy,
    UIElementObservation,
)
from teach_a_skill.recovery.planner import RecoveryPlanner
from teach_a_skill.recovery.verification import VerificationEngine
from teach_a_skill.skill.models import SkillActionType, SkillStep

logger = logging.getLogger(__name__)


def get_current_rss_mb() -> float:
    """Return resident set size in megabytes."""
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    # On macOS ru_maxrss is in bytes, on Linux in kilobytes
    import sys
    if sys.platform == "darwin":
        return rusage.ru_maxrss / (1024 * 1024)
    return rusage.ru_maxrss / 1024


class RecoveryBenchmark:
    """Benchmark suite for Phase 11 recovery engine."""

    def __init__(self) -> None:
        self.classifier = FailureClassifier()
        self.planner = RecoveryPlanner()
        self.verifier = VerificationEngine()

    def benchmark_classification(self, counts: list[int] = [100, 1000, 10000]) -> dict[str, Any]:
        """Benchmark failure classification latency and memory scaling."""
        results = {}
        step = SkillStep(
            step_id="step_bench",
            ordinal=0,
            target="button",
            description="click button",
            action_type=SkillActionType.SELECT,
        )
        action = PlannedAction(
            action_id="act_bench",
            step_id="step_bench",
            action_type=ActionType.CLICK,
            target_x=10.0,
            target_y=10.0,
            safety_level=SafetyLevel.SAFE,
        )
        step_res = StepExecutionResult(
            step_id="step_bench",
            action_id="act_bench",
            action_type=ActionType.CLICK,
            status=StepStatus.FAILED,
            error_message="target disappeared from ui",
        )
        snap = EnvironmentSnapshot(
            snapshot_id="snap_bench",
            active_application="TextEdit",
            elements=[],
        )

        for count in counts:
            rss_start = get_current_rss_mb()
            start_time = time.perf_counter()

            for i in range(count):
                self.classifier.classify_failure(
                    execution_id=f"exec_bench_{i}",
                    step=step,
                    action=action,
                    step_result=step_res,
                    snapshot_before=snap,
                    snapshot_after=snap,
                    raw_error="target disappeared",
                )

            duration = time.perf_counter() - start_time
            rss_end = get_current_rss_mb()
            rate = count / duration if duration > 0 else 0.0

            results[f"count_{count}"] = {
                "count": count,
                "duration_seconds": round(duration, 4),
                "classifications_per_sec": round(rate, 2),
                "rss_mb": round(rss_end, 2),
                "rss_delta_mb": round(rss_end - rss_start, 2),
            }

        return results

    def benchmark_planning(self, step_counts: list[int] = [10, 50, 100]) -> dict[str, Any]:
        """Benchmark recovery plan formulation latency."""
        results = {}
        budget = RecoveryBudget(step_retry_budget=10, execution_retry_budget=100)

        for count in step_counts:
            failures = [
                self.classifier.classify_failure(
                    execution_id=f"exec_{i}",
                    step=SkillStep(
                        step_id=f"s_{i}",
                        ordinal=i,
                        target="text",
                        description="type",
                        action_type=SkillActionType.INPUT,
                    ),
                    action=None,
                    step_result=None,
                    snapshot_before=None,
                    snapshot_after=None,
                    raw_error="temporary loading",
                )
                for i in range(count)
            ]

            start_time = time.perf_counter()
            for fail in failures:
                self.planner.plan_recovery(
                    failure=fail,
                    step=SkillStep(
                        step_id=fail.step_id,
                        ordinal=0,
                        target="text",
                        description="type",
                        action_type=SkillActionType.INPUT,
                    ),
                    last_action=None,
                    budget=budget,
                )
            duration = time.perf_counter() - start_time

            results[f"steps_{count}"] = {
                "steps": count,
                "duration_ms": round(duration * 1000, 2),
                "avg_per_step_ms": round((duration * 1000) / count, 4),
            }

        return results

    def benchmark_verification(self, candidate_counts: list[int] = [10, 100, 1000]) -> dict[str, Any]:
        """Benchmark multi-source verification engine."""
        results = {}
        step = SkillStep(
            step_id="step_ver",
            ordinal=0,
            target="Save Document",
            description="verify button",
            action_type=SkillActionType.SELECT,
            arguments={"expected_application": "TextEdit", "expected_text": "Save Document"},
        )

        for count in candidate_counts:
            elements = [
                EnvironmentElement(
                    element_id=f"el_{i}",
                    role="button",
                    label=f"Button {i}" if i != 5 else "Save Document",
                    pixel_x=10.0,
                    pixel_y=20.0,
                    pixel_width=50.0,
                    pixel_height=20.0,
                )
                for i in range(count)
            ]
            snap = EnvironmentSnapshot(
                snapshot_id=f"snap_{count}",
                active_application="TextEdit",
                elements=elements,
            )

            start_time = time.perf_counter()
            res = self.verifier.verify_step_postconditions(step, snap, ocr_text="Save Document")
            duration = time.perf_counter() - start_time

            results[f"candidates_{count}"] = {
                "candidate_count": count,
                "duration_ms": round(duration * 1000, 3),
                "verified": res.verified,
                "confidence": round(res.confidence, 4),
            }

        return results

    def benchmark_long_run_stability(self, cycles: int = 500) -> dict[str, Any]:
        """Verify memory boundedness and leak freedom across 500 recovery cycles."""
        rss_initial = get_current_rss_mb()
        step = SkillStep(
            step_id="step_long",
            ordinal=0,
            target="button",
            description="click",
            action_type=SkillActionType.SELECT,
        )
        action = PlannedAction(
            action_id="act_long",
            step_id="step_long",
            action_type=ActionType.CLICK,
            target_x=10.0,
            target_y=10.0,
            safety_level=SafetyLevel.SAFE,
        )

        start_time = time.perf_counter()
        for i in range(cycles):
            budget = RecoveryBudget(step_retry_budget=5, execution_retry_budget=20)
            fail = self.classifier.classify_failure(
                execution_id=f"exec_long_{i}",
                step=step,
                action=action,
                step_result=None,
                snapshot_before=None,
                snapshot_after=None,
                raw_error="target renamed to Save Document",
            )
            plan = self.planner.plan_recovery(
                failure=fail,
                step=step,
                last_action=action,
                budget=budget,
            )
            assert plan is not None

        duration = time.perf_counter() - start_time
        rss_final = get_current_rss_mb()
        rss_growth = rss_final - rss_initial

        return {
            "cycles": cycles,
            "duration_seconds": round(duration, 4),
            "initial_rss_mb": round(rss_initial, 2),
            "final_rss_mb": round(rss_final, 2),
            "growth_mb": round(rss_growth, 2),
            "memory_bounded": rss_growth < 50.0,
        }

    def run_all(self) -> dict[str, Any]:
        """Execute full benchmark suite."""
        return {
            "classification": self.benchmark_classification(),
            "planning": self.benchmark_planning(),
            "verification": self.benchmark_verification(),
            "long_run": self.benchmark_long_run_stability(500),
        }
