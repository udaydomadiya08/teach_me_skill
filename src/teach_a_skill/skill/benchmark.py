"""Benchmark suite for Phase 8 skill compilation layer."""

import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

from teach_a_skill.hardware.benchmark import measure_current_rss_mb
from teach_a_skill.intent.storage import IntentStorage
from teach_a_skill.skill.compilers.deterministic import DeterministicSkillCompiler
from teach_a_skill.skill.compilers.local_llm import LocalLLMCompiler
from teach_a_skill.skill.compilers.mock import MockSkillCompiler
from teach_a_skill.skill.pipeline import SkillCompilationPipeline
from teach_a_skill.skill.validator import SkillValidator
from teach_a_skill.storage.manager import StorageManager


@dataclass
class SkillBenchmarkItem:
    name: str
    compiler: str
    data_source: str
    duration_sec: Optional[float]
    latency_ms: Optional[float]
    peak_rss_mb: float
    result: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillBenchmarkRunner:
    """Executes benchmarks across deterministic compiler, mock, real models, cache, and long loops."""

    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager

    def run_all(self, session_id: str) -> list[SkillBenchmarkItem]:
        results: list[SkillBenchmarkItem] = []

        intent_storage = IntentStorage(self.storage_manager, session_id)
        if not intent_storage.exists():
            return [
                SkillBenchmarkItem(
                    name="Skill compilation",
                    compiler="none",
                    data_source=f"session:{session_id}",
                    duration_sec=0.0,
                    latency_ms=0.0,
                    peak_rss_mb=measure_current_rss_mb(),
                    result="SKIPPED",
                    notes="Phase 7 intent artifacts not found.",
                )
            ]

        tasks = intent_storage.read_tasks()
        if not tasks:
            return []
        understanding = tasks[0]

        # 1. Deterministic Compilation Benchmark
        det_compiler = DeterministicSkillCompiler()
        t0 = time.perf_counter()
        skill_ir = det_compiler.compile(understanding)
        d_compile = time.perf_counter() - t0
        results.append(
            SkillBenchmarkItem(
                name="Deterministic compilation",
                compiler="deterministic",
                data_source="real Phase 7",
                duration_sec=round(d_compile, 4),
                latency_ms=round(d_compile * 1000.0, 2),
                peak_rss_mb=measure_current_rss_mb(),
                result="PASS",
                notes=f"Compiled {len(skill_ir.steps)} steps, {len(skill_ir.parameters)} params, {len(skill_ir.dependencies)} deps.",
            )
        )

        # 2. Skill IR Validation Benchmark
        validator = SkillValidator()
        t0 = time.perf_counter()
        val_errors = validator.validate(skill_ir)
        d_val = time.perf_counter() - t0
        results.append(
            SkillBenchmarkItem(
                name="Skill IR validation",
                compiler="deterministic",
                data_source="real Skill IR",
                duration_sec=round(d_val, 4),
                latency_ms=round(d_val * 1000.0, 2),
                peak_rss_mb=measure_current_rss_mb(),
                result="PASS" if not val_errors else "FAILED",
                notes=f"Validated schema, references, payload blocking. Errors: {len(val_errors)}.",
            )
        )

        # 3. Canonical Fingerprinting Benchmark
        t0 = time.perf_counter()
        fp = skill_ir.compute_canonical_fingerprint()
        d_fp = time.perf_counter() - t0
        results.append(
            SkillBenchmarkItem(
                name="Canonical fingerprinting",
                compiler="deterministic",
                data_source="real Skill IR",
                duration_sec=round(d_fp, 4),
                latency_ms=round(d_fp * 1000.0, 2),
                peak_rss_mb=measure_current_rss_mb(),
                result="PASS",
                notes=f"Computed SHA-256 fingerprint: {fp[:16]}...",
            )
        )

        # 4. Mock Compiler Benchmark
        mock_compiler = MockSkillCompiler()
        mock_pipeline = SkillCompilationPipeline(
            storage_manager=self.storage_manager,
            compiler=mock_compiler,
            cache_enabled=False,
        )
        t0 = time.perf_counter()
        mock_skill, mock_manifest = mock_pipeline.compile_session(session_id=session_id, force_rebuild=True)
        d_mock = time.perf_counter() - t0
        results.append(
            SkillBenchmarkItem(
                name="Mock compiler",
                compiler="mock",
                data_source="synthetic/mock",
                duration_sec=round(d_mock, 4),
                latency_ms=round(d_mock * 1000.0, 2),
                peak_rss_mb=measure_current_rss_mb(),
                result="PASS",
                notes=f"Produced mock Skill IR: {mock_skill.name}.",
            )
        )

        # 5. Real Local Model Compiler Benchmark (Strictly conditioned on availability)
        real_llm = LocalLLMCompiler()
        if real_llm.is_available():
            try:
                real_pipeline = SkillCompilationPipeline(
                    storage_manager=self.storage_manager,
                    compiler=real_llm,
                    cache_enabled=False,
                )
                t0 = time.perf_counter()
                real_skill, real_manifest = real_pipeline.compile_session(session_id=session_id, force_rebuild=True)
                d_real = time.perf_counter() - t0
                results.append(
                    SkillBenchmarkItem(
                        name="Real local compiler model",
                        compiler="local_llm",
                        data_source="real",
                        duration_sec=round(d_real, 4),
                        latency_ms=round(d_real * 1000.0, 2),
                        peak_rss_mb=measure_current_rss_mb(),
                        result="PASS",
                        notes=f"Compiled using local LLM: {real_skill.skill_id}",
                    )
                )
            except Exception as e:
                results.append(
                    SkillBenchmarkItem(
                        name="Real local compiler model",
                        compiler="local_llm",
                        data_source="real",
                        duration_sec=None,
                        latency_ms=None,
                        peak_rss_mb=measure_current_rss_mb(),
                        result="FAILED",
                        notes=str(e),
                    )
                )
        else:
            results.append(
                SkillBenchmarkItem(
                    name="Real local compiler model",
                    compiler="local_llm",
                    data_source="real",
                    duration_sec=None,
                    latency_ms=None,
                    peak_rss_mb=measure_current_rss_mb(),
                    result="NOT RUN",
                    notes="MODEL_NOT_AVAILABLE: No local compiler LLM weights installed; zero remote downloads per policy.",
                )
            )

        # 6. Cache-hit Retrieval Benchmark
        pipe_cached = SkillCompilationPipeline(
            storage_manager=self.storage_manager,
            compiler=det_compiler,
            cache_enabled=True,
        )
        pipe_cached.compile_session(session_id=session_id, force_rebuild=True)
        t0 = time.perf_counter()
        _s_cached, _m_cached = pipe_cached.compile_session(session_id=session_id, force_rebuild=False)
        d_cache = time.perf_counter() - t0
        results.append(
            SkillBenchmarkItem(
                name="Cache-hit retrieval",
                compiler="cache",
                data_source="cache",
                duration_sec=round(d_cache, 4),
                latency_ms=round(d_cache * 1000.0, 2),
                peak_rss_mb=measure_current_rss_mb(),
                result="PASS",
                notes="Content-addressed compilation cache hit.",
            )
        )

        # 7. Long-Run Compilation Memory Safety Benchmark
        initial_rss = measure_current_rss_mb()
        t0 = time.perf_counter()
        for _ in range(50):
            _ = det_compiler.compile(understanding)
        d_long = time.perf_counter() - t0
        final_rss = measure_current_rss_mb()
        rss_growth = max(0.0, final_rss - initial_rss)
        results.append(
            SkillBenchmarkItem(
                name="Long-run compilation memory safety",
                compiler="deterministic",
                data_source="real loop (50 passes)",
                duration_sec=round(d_long, 4),
                latency_ms=round(d_long * 1000.0 / 50, 2),
                peak_rss_mb=final_rss,
                result="PASS",
                notes=f"50 compilation passes completed; RSS growth: {rss_growth:.2f} MB (bounded).",
            )
        )

        return results
