"""Performance and stress benchmarks for demonstration recorder."""

import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from teach_a_skill.hardware.benchmark import measure_current_rss_mb
from teach_a_skill.recorder.recorder import UniversalRecorder
from teach_a_skill.recorder.screen import CaptureProfile
from teach_a_skill.recorder.sensitive import SensitiveInputPolicy
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.storage.manager import StorageManager


@dataclass(frozen=True)
class RecorderBenchmarkReport:
    idle_ram_mb: float
    recording_ram_mb: float
    idle_cpu_percent: float
    recording_cpu_percent: float
    synthetic_1min_events: int
    synthetic_1min_duration_sec: float
    synthetic_1min_events_per_sec: float
    storage_mb_per_minute: float
    frames_per_minute: float
    high_throughput_events_per_sec: float
    crash_recovery_time_ms: float
    memory_growth_mb: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_recorder_benchmark(storage_manager: StorageManager) -> RecorderBenchmarkReport:
    """Run comprehensive performance, throughput, and stress benchmarks on recorder."""
    # 1. Measure initial idle RAM and CPU
    idle_ram = measure_current_rss_mb()
    t_cpu_start = time.process_time()
    t_wall_start = time.perf_counter()
    time.sleep(0.05)
    t_cpu_end = time.process_time()
    t_wall_end = time.perf_counter()
    idle_cpu = round(((t_cpu_end - t_cpu_start) / (t_wall_end - t_wall_start)) * 100, 2)

    # 2. Benchmark realistic session (simulating 1 minute of user demonstration)
    session_id_1min = f"bench_1min_{int(time.time())}"
    rec = UniversalRecorder(
        storage_manager=storage_manager,
        capture_profile=CaptureProfile.BALANCED,
        sensitive_policy=SensitiveInputPolicy.RECORD,
    )

    t_rec_cpu_start = time.process_time()
    t_rec_wall_start = time.perf_counter()

    # Generate 500 events (typical 1-minute activity at ~8 events/sec) in fast-forward
    rec.start_recording(
        session_id=session_id_1min,
        use_synthetic_source=True,
        synthetic_event_count=500,
        synthetic_rate_hz=1000.0,  # Fast forward
    )

    # Allow synthetic generator to finish
    while rec._active_source and rec._active_source.is_active:
        time.sleep(0.01)

    _ = rec.stop_recording()

    t_rec_cpu_end = time.process_time()
    t_rec_wall_end = time.perf_counter()

    wall_duration = t_rec_wall_end - t_rec_wall_start
    cpu_duration = t_rec_cpu_end - t_rec_cpu_start
    rec_cpu = round((cpu_duration / wall_duration) * 100, 2) if wall_duration > 0 else 0.0
    rec_ram = measure_current_rss_mb()

    # Calculate on-disk storage size
    session_dir = storage_manager.get_path("recordings", session_id_1min)
    total_bytes = 0
    frame_count = 0
    for root, _, files in os.walk(session_dir):
        for f in files:
            fp = os.path.join(root, f)
            total_bytes += os.path.getsize(fp)
            if f.endswith(".png"):
                frame_count += 1

    storage_mb = total_bytes / (1024 * 1024)
    # Extrapolate to 1 minute
    storage_mb_per_min = round(storage_mb * (60.0 / max(1.0, wall_duration)), 2)
    frames_per_min = round(frame_count * (60.0 / max(1.0, wall_duration)), 1)
    ev_per_sec = round(500 / max(0.01, wall_duration), 1)

    # 3. High-throughput event stress test (10,000 events)
    session_id_stress = f"bench_stress_{int(time.time())}"
    rec_stress = UniversalRecorder(
        storage_manager=storage_manager,
        capture_profile=CaptureProfile.MINIMAL,
    )
    rec_stress.start_recording(
        session_id=session_id_stress,
        use_synthetic_source=True,
        synthetic_event_count=5000,
        synthetic_rate_hz=20000.0,
    )

    t_stress_start = time.perf_counter()
    while rec_stress._active_source and rec_stress._active_source.is_active:
        time.sleep(0.005)
    rec_stress.stop_recording()
    t_stress_end = time.perf_counter()

    stress_duration = t_stress_end - t_stress_start
    high_throughput_eps = round(5000 / max(0.001, stress_duration), 1)

    ram_after_stress = measure_current_rss_mb()
    memory_growth = max(0.0, round(ram_after_stress - idle_ram, 2))

    # 4. Crash recovery benchmark
    # Simulate an interrupted session (write events without stop marker)
    crash_session_id = f"bench_crash_{int(time.time())}"
    rec_crash = UniversalRecorder(
        storage_manager=storage_manager,
        capture_profile=CaptureProfile.MINIMAL,
    )
    rec_crash.start_recording(
        session_id=crash_session_id,
        use_synthetic_source=True,
        synthetic_event_count=50,
        synthetic_rate_hz=500.0,
    )
    time.sleep(0.05)
    # Simulate crash by closing file handle without normal stop
    rec_crash._session_storage.close()

    t_recov_start = time.perf_counter()
    _ = SessionStorage.recover_session(storage_manager, crash_session_id)
    t_recov_end = time.perf_counter()
    recovery_ms = round((t_recov_end - t_recov_start) * 1000, 2)

    return RecorderBenchmarkReport(
        idle_ram_mb=idle_ram,
        recording_ram_mb=rec_ram,
        idle_cpu_percent=idle_cpu,
        recording_cpu_percent=rec_cpu,
        synthetic_1min_events=500,
        synthetic_1min_duration_sec=round(wall_duration, 2),
        synthetic_1min_events_per_sec=ev_per_sec,
        storage_mb_per_minute=storage_mb_per_min,
        frames_per_minute=frames_per_min,
        high_throughput_events_per_sec=high_throughput_eps,
        crash_recovery_time_ms=recovery_ms,
        memory_growth_mb=memory_growth,
    )
