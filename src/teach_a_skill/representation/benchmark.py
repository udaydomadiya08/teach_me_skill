"""Phase 4 performance, memory footprint, and query latency benchmark runner."""

import gc
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.benchmark import measure_current_rss_mb
from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.recorder.session import SessionManifest, SessionState
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.representation.builder import RepresentationBuilder
from teach_a_skill.representation.demonstration import Demonstration
from teach_a_skill.representation.query import RepresentationQueryEngine
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation
from teach_a_skill.teaching.session import TeachingManifest, TeachingState
from teach_a_skill.teaching.storage import TeachingStorage
from teach_a_skill.teaching.transcript.segment import TranscriptSegment

logger = get_logger("teach_a_skill.representation.benchmark")


@dataclass
class RepresentationBenchmarkReport:
    """Quantitative performance and resource metrics for Phase 4 canonical representation."""

    build_time_ms: float
    idle_ram_mb: float
    peak_ram_mb: float
    memory_growth_mb: float
    raw_session_bytes: int
    representation_bytes: int
    storage_ratio_percent: float
    single_event_lookup_us: float
    timestamp_range_lookup_us: float
    segment_lookup_us: float
    context_window_lookup_us: float
    total_events: int
    total_timeline_items: int
    total_segments: int
    total_relations: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def print_summary(self) -> None:
        print("\nPhase 4 Canonical Representation Performance Benchmark")
        print("======================================================")
        print(f"Build Latency:                {self.build_time_ms:.2f} ms")
        print(f"Idle Process RAM (RSS):       {self.idle_ram_mb:.2f} MB")
        print(f"Peak Process RAM (RSS):       {self.peak_ram_mb:.2f} MB")
        print(f"Memory Growth:                {self.memory_growth_mb:.2f} MB")
        print(f"Raw Session Footprint:        {self.raw_session_bytes / 1024:.1f} KB")
        print(f"Canonical Rep. Footprint:     {self.representation_bytes / 1024:.1f} KB")
        print(f"Storage Ratio (Rep / Raw):    {self.storage_ratio_percent:.1f}%")
        print("\nQuery Engine Latencies:")
        print(f"  • Single Event Lookup:      {self.single_event_lookup_us:.2f} µs")
        print(f"  • Timestamp Range Query:    {self.timestamp_range_lookup_us:.2f} µs")
        print(f"  • Segment Lookup:           {self.segment_lookup_us:.2f} µs")
        print(f"  • AI Context Window Query:  {self.context_window_lookup_us:.2f} µs")
        print("\nRepresentation Structure:")
        print(f"  • Total Canonical Events:   {self.total_events}")
        print(f"  • Unified Timeline Items:   {self.total_timeline_items}")
        print(f"  • Demonstration Segments:   {self.total_segments}")
        print(f"  • Temporal Relations:       {self.total_relations}\n")


def run_representation_benchmark(storage_manager: StorageManager) -> RepresentationBenchmarkReport:
    """Run comprehensive performance, memory, and query benchmarks for Phase 4."""
    session_id = f"bench_rep_{int(time.time())}"

    # 1. Synthesize Phase 2 Raw Demonstration Evidence
    sess_storage = SessionStorage(storage_manager, session_id)
    manifest = SessionManifest(
        session_id=session_id,
        platform="macos",
        architecture="arm64",
        status=SessionState.COMPLETED,
        duration_sec=60.0,
        display_configuration=[{"width": 1920, "height": 1080}],
    )
    sess_storage.initialize_session_layout(manifest)

    # 500 events over 60 seconds
    for i in range(1, 501):
        t_mono = (i / 500.0) * 60.0
        if i % 50 == 1:
            evt_type = EventType.WINDOW_FOCUS_CHANGED
            payload = {"app_name": f"App_{i // 50}", "title": f"Window_{i // 50}"}
        elif i % 10 == 0:
            evt_type = EventType.MOUSE_CLICK
            payload = {"button": "left", "x": (i * 3) % 1920, "y": (i * 2) % 1080}
        elif i % 7 == 0:
            evt_type = EventType.KEY_DOWN
            payload = {"key": "a"}
        else:
            evt_type = EventType.MOUSE_MOVE
            payload = {"x": (i * 3) % 1920, "y": (i * 2) % 1080}

        ev = Event(
            event_id=f"raw_evt_{i:05d}",
            session_id=session_id,
            sequence_number=i,
            timestamp=f"2026-10-04T12:00:{int(t_mono):02d}Z",
            monotonic_timestamp=t_mono,
            event_type=evt_type,
            priority=EventPriority.MEDIUM,
            source="system",
            payload=payload,
        )
        sess_storage.append_event(ev)

    sess_storage.close()

    # Synthetic frame index
    frames = [
        {"frame_id": f"f_{j:03d}", "monotonic_timestamp": j * 2.0, "path": f"frames/f_{j:03d}.webp"}
        for j in range(30)
    ]
    sess_storage.storage_manager.write_metadata(
        sess_storage.metadata_dir / "frame_index.json", {"frames": frames}
    )

    # 2. Synthesize Phase 3 Teaching Evidence
    t_storage = TeachingStorage(storage_manager, session_id)
    t_manifest = TeachingManifest(
        teaching_session_id=f"teach_{session_id}",
        recording_session_id=session_id,
        status=TeachingState.COMPLETED,
    )
    t_storage.initialize_teaching_layout(t_manifest)

    for k in range(1, 15):
        seg = TranscriptSegment(
            segment_id=f"sp_seg_{k:03d}",
            teaching_session_id=f"teach_{session_id}",
            sequence_number=k,
            start_monotonic_ns=int(k * 4.0 * 1_000_000_000),
            end_monotonic_ns=int((k * 4.0 + 2.5) * 1_000_000_000),
            start_wall_time="2026-10-04T12:00:00Z",
            end_wall_time="2026-10-04T12:00:02Z",
            text=f"Teaching instruction step {k}.",
        )
        t_storage.transcript_store.append_segment(seg)

    for m in range(1, 6):
        ann = TeachingAnnotation(
            annotation_id=f"ann_{m:03d}",
            teaching_session_id=f"teach_{session_id}",
            created_monotonic_ns=int(m * 10.0 * 1_000_000_000),
            start_monotonic_ns=int(m * 10.0 * 1_000_000_000),
            end_monotonic_ns=int((m * 10.0 + 1.0) * 1_000_000_000),
            text=f"User note {m}",
            type=AnnotationType.INSTRUCTION,
        )
        t_storage.annotation_store.append_annotation(ann)

    # Compute raw evidence size
    raw_bytes = sum(f.stat().st_size for f in sess_storage.session_dir.rglob("*") if f.is_file())

    # 3. Benchmark Representation Build
    gc.collect()
    idle_ram = measure_current_rss_mb()

    builder = RepresentationBuilder(storage_manager)
    t0 = time.perf_counter()
    _ = builder.build_representation(session_id, force_rebuild=True)
    build_time_ms = (time.perf_counter() - t0) * 1000.0

    peak_ram = measure_current_rss_mb()
    growth_mb = max(0.0, round(peak_ram - idle_ram, 2))

    rep_storage = RepresentationStorage(storage_manager, session_id)
    rep_bytes = sum(f.stat().st_size for f in rep_storage.representation_dir.rglob("*") if f.is_file())
    ratio_pct = round((rep_bytes / max(1, raw_bytes)) * 100.0, 1)

    # 4. Benchmark Query Latencies
    query_engine = RepresentationQueryEngine(storage_manager, session_id)

    # Single event lookup
    t_ev = time.perf_counter()
    for _ in range(200):
        _ = query_engine.get_event("raw_evt_00100")
    ev_latency_us = ((time.perf_counter() - t_ev) / 200) * 1_000_000

    # Range query
    t_rng = time.perf_counter()
    for _ in range(200):
        _ = query_engine.get_timeline_items(10_000_000_000, 30_000_000_000)
    rng_latency_us = ((time.perf_counter() - t_rng) / 200) * 1_000_000

    # Segment query
    t_seg = time.perf_counter()
    for _ in range(200):
        _ = query_engine.get_segment("seg_0001")
    seg_latency_us = ((time.perf_counter() - t_seg) / 200) * 1_000_000

    # Context window query
    t_ctx = time.perf_counter()
    for _ in range(100):
        _ = query_engine.get_context_window(20_000_000_000, 2000.0, 2000.0)
    ctx_latency_us = ((time.perf_counter() - t_ctx) / 100) * 1_000_000

    demo = Demonstration.load(session_id, storage_manager)

    return RepresentationBenchmarkReport(
        build_time_ms=round(build_time_ms, 2),
        idle_ram_mb=round(idle_ram, 2),
        peak_ram_mb=round(peak_ram, 2),
        memory_growth_mb=growth_mb,
        raw_session_bytes=raw_bytes,
        representation_bytes=rep_bytes,
        storage_ratio_percent=ratio_pct,
        single_event_lookup_us=round(ev_latency_us, 2),
        timestamp_range_lookup_us=round(rng_latency_us, 2),
        segment_lookup_us=round(seg_latency_us, 2),
        context_window_lookup_us=round(ctx_latency_us, 2),
        total_events=demo.summary.total_canonical_events,
        total_timeline_items=len(demo.timeline),
        total_segments=demo.summary.total_segments,
        total_relations=len(demo.relations),
    )
