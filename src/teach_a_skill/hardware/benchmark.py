"""Baseline performance and latency benchmark."""

import resource
import time
from dataclasses import asdict, dataclass
from typing import Any

from teach_a_skill.hardware.detector import HardwareDetector


@dataclass(frozen=True)
class BenchmarkReport:
    startup_time_ms: float
    hardware_detection_time_ms: float
    health_check_time_ms: float
    idle_ram_rss_mb: float
    idle_cpu_percent: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def measure_current_rss_mb() -> float:
    """Measure resident set size (RSS) in megabytes of current process."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # On macOS, ru_maxrss is in bytes; on Linux, it is in kilobytes
    import platform

    if platform.system().lower() == "darwin":
        return round(usage.ru_maxrss / (1024 * 1024), 2)
    return round(usage.ru_maxrss / 1024, 2)


def run_benchmark(run_health_check_fn: Any = None) -> BenchmarkReport:
    """Run baseline latency and footprint measurement."""
    # 1. Measure hardware detection time
    t0 = time.perf_counter()
    detector = HardwareDetector()
    _ = detector.get_profile()
    t1 = time.perf_counter()
    hw_detection_ms = round((t1 - t0) * 1000, 2)

    # 2. Measure health check time if provided
    health_check_ms = 0.0
    if run_health_check_fn:
        t_health0 = time.perf_counter()
        _ = run_health_check_fn()
        t_health1 = time.perf_counter()
        health_check_ms = round((t_health1 - t_health0) * 1000, 2)

    # 3. Measure memory footprint
    rss_mb = measure_current_rss_mb()

    # 4. Measure idle CPU time (process times over 50ms)
    t_cpu_start = time.process_time()
    t_wall_start = time.perf_counter()
    time.sleep(0.05)  # Idle 50ms
    t_cpu_end = time.process_time()
    t_wall_end = time.perf_counter()

    wall_delta = t_wall_end - t_wall_start
    cpu_delta = t_cpu_end - t_cpu_start
    cpu_percent = round((cpu_delta / wall_delta) * 100, 2) if wall_delta > 0 else 0.0

    return BenchmarkReport(
        startup_time_ms=hw_detection_ms,  # Phase 1 startup is dominated by initialization
        hardware_detection_time_ms=hw_detection_ms,
        health_check_time_ms=health_check_ms,
        idle_ram_rss_mb=rss_mb,
        idle_cpu_percent=cpu_percent,
    )
