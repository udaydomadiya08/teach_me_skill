"""Synthetic learning benchmarks, stress testing, and RSS memory stability."""

from __future__ import annotations

import resource
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from teach_a_skill.learning.candidate import CandidateBuilder, ShadowEvaluator, VersionComparator
from teach_a_skill.learning.detector import FailurePatternDetector, VariationDetector
from teach_a_skill.learning.models import (
    CandidateSkillVersion,
    ExecutionRecord,
    ImprovementProposal,
    PromotionPolicy,
)
from teach_a_skill.learning.promotion import PromotionManager
from teach_a_skill.learning.proposal import ImprovementGenerator
from teach_a_skill.learning.tracker import PerformanceTracker


def get_current_rss_mb() -> float:
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform == "darwin":
        return round(rusage.ru_maxrss / (1024 * 1024), 2)
    return round(rusage.ru_maxrss / 1024, 2)


@dataclass
class Phase13BenchmarkResults:
    """Benchmark metrics for Phase 13 Learning Subsystem."""

    ingestion_rate_1k: float = 0.0
    ingestion_rate_10k: float = 0.0
    ingestion_rate_100k: float = 0.0
    pattern_detection_ms: float = 0.0
    proposal_generation_ms: float = 0.0
    cycles_completed: int = 0
    cycle_rate: float = 0.0
    initial_rss_mb: float = 0.0
    peak_rss_mb: float = 0.0
    final_rss_mb: float = 0.0
    rss_growth_mb: float = 0.0
    memory_bounded: bool = True
    false_positive_rejected: bool = False
    false_negative_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LearningBenchmarkRunner:
    """Orchestrates comprehensive Phase 13 benchmarks, stress tests, and planted pattern verification."""

    @classmethod
    def run_all(cls) -> Phase13BenchmarkResults:
        initial_rss = get_current_rss_mb()
        peak_rss = initial_rss

        tracker = PerformanceTracker()
        detector = FailurePatternDetector(min_frequency=3, min_sample_size=4)
        generator = ImprovementGenerator()

        # 1. False-Positive Test (Section 53): Random unrelated failures should NOT trigger a pattern
        random_records = [
            ExecutionRecord(
                execution_id=f"rand-{i}",
                skill_id="skill_fp_test",
                skill_version="1.0.0",
                final_outcome="FAILED",
                failure_types=[f"UNIQUE_ERROR_{i}"],
                verification_results=[{"step_id": f"step_{i}", "passed": False}],
            )
            for i in range(5)
        ]
        fp_patterns = detector.detect_patterns("skill_fp_test", random_records)
        fp_proposals = generator.generate_proposals("skill_fp_test", "1.0.0", fp_patterns, [])
        false_positive_clean = (len(fp_patterns) == 0 and len(fp_proposals) == 0)

        # 2. False-Negative Test (Section 54): Repeated known failure must be detected
        known_records = [
            ExecutionRecord(
                execution_id=f"known-{i}",
                skill_id="skill_fn_test",
                skill_version="1.0.0",
                final_outcome="FAILED" if i < 4 else "SUCCESS",
                failure_types=["TARGET_NOT_FOUND"] if i < 4 else [],
                verification_results=[{"step_id": "step_button", "passed": i >= 4}],
            )
            for i in range(6)
        ]
        fn_patterns = detector.detect_patterns("skill_fn_test", known_records)
        false_negative_clean = len(fn_patterns) >= 1 and fn_patterns[0].affected_step == "step_button"

        # 3. Scaling Benchmark: Ingestion (1,000, 10,000, 100,000 synthetic records)
        rates: dict[str, float] = {}
        for count in (1000, 10000, 100000):
            t0 = time.time()
            batch_tracker = PerformanceTracker()
            for i in range(count):
                rec = ExecutionRecord(
                    execution_id=f"scale-{i}",
                    skill_id="scale_skill",
                    skill_version="1.0.0",
                    final_outcome="SUCCESS" if i % 10 != 0 else "FAILED",
                    execution_duration=0.1,
                )
                batch_tracker.record_execution(rec)
            dur = max(time.time() - t0, 0.0001)
            rates[str(count)] = round(count / dur, 2)
            peak_rss = max(peak_rss, get_current_rss_mb())

        # 4. Latency Measurements: Pattern Detection & Proposal Generation
        t0 = time.time()
        patterns = detector.detect_patterns("scale_skill", batch_tracker.get_records("scale_skill")[:1000])
        pattern_ms = (time.time() - t0) * 1000.0

        t0 = time.time()
        proposals = generator.generate_proposals("scale_skill", "1.0.0", patterns, [])
        proposal_ms = (time.time() - t0) * 1000.0

        # 5. Long-Run Stress Test: 1,000 learning cycles (Section 64)
        base_ir = {
            "skill_id": "stress_skill",
            "version": "1.0.0",
            "steps": [{"step_id": "step_main", "target_element": {"label": "Save", "aliases": []}}],
        }
        pm = PromotionManager(PromotionPolicy(minimum_executions=2, minimum_success_improvement=0.01))
        t0 = time.time()
        for c in range(1000):
            rec = ExecutionRecord(
                execution_id=f"cycle-rec-{c}",
                skill_id="stress_skill",
                skill_version="1.0.0",
                final_outcome="FAILED" if c % 5 == 0 else "SUCCESS",
                failure_types=["TARGET_NOT_FOUND"] if c % 5 == 0 else [],
                verification_results=[{"step_id": "step_main", "passed": c % 5 != 0}],
            )
            tracker.record_execution(rec)
            if c % 100 == 0:
                pats = detector.detect_patterns("stress_skill", tracker.get_records("stress_skill")[-20:])
                props = generator.generate_proposals("stress_skill", "1.0.0", pats, [])
                if props:
                    cand = CandidateBuilder.build_candidate(base_ir, props[0])
                    eval_res = ShadowEvaluator.evaluate_candidate(cand, tracker.get_records("stress_skill")[-20:])
                    metrics = tracker.compute_metrics("stress_skill", "1.0.0")
                    comp = VersionComparator.compare(metrics, eval_res)
                    if comp["is_improved"]:
                        try:
                            _ = pm.promote_candidate(cand, comp, operator_approved=True)
                        except Exception:
                            pass
                peak_rss = max(peak_rss, get_current_rss_mb())

        cycle_dur = max(time.time() - t0, 0.0001)
        cycle_rate = round(1000.0 / cycle_dur, 2)

        final_rss = get_current_rss_mb()
        growth = max(0.0, round(final_rss - initial_rss, 2))
        bounded = growth < 200.0

        return Phase13BenchmarkResults(
            ingestion_rate_1k=rates.get("1000", 0.0),
            ingestion_rate_10k=rates.get("10000", 0.0),
            ingestion_rate_100k=rates.get("100000", 0.0),
            pattern_detection_ms=round(pattern_ms, 2),
            proposal_generation_ms=round(proposal_ms, 2),
            cycles_completed=1000,
            cycle_rate=cycle_rate,
            initial_rss_mb=initial_rss,
            peak_rss_mb=peak_rss,
            final_rss_mb=final_rss,
            rss_growth_mb=growth,
            memory_bounded=bounded,
            false_positive_rejected=false_positive_clean,
            false_negative_detected=false_negative_clean,
        )
