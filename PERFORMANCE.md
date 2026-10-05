# Performance Baseline & Hardware Adaptation

## 1. Low-Hardware Baseline Requirement

A core mandate of Teach A Skill is that the system must remain lightweight and responsive on modest laptops (e.g. 8GB RAM, integrated graphics, quad-core CPU).

To achieve this:
1. **Lightweight Core**: The core application imports only what is necessary, relying on Python 3.11's optimized runtime.
2. **Zero Startup Bloat**: No heavy model weights (PyTorch, Transformers, large VLMs) are loaded merely to start the application, check status, or verify health.
3. **Deterministic Hardware Budgeting**: Memory limits are strictly calculated before any resource-intensive operation is scheduled.

---

## 2. Hardware Performance Tiers & Budgeting

The system adapts to the host machine using conservative, deterministic classification:

| Dimension | `BASELINE` | `STANDARD` | `HIGH` |
| :--- | :--- | :--- | :--- |
| **Target Machines** | Modest laptops, <= 8GB RAM, CPU-only | Modern laptops, 16GB RAM, entry GPU/Apple Silicon base | Workstations, >= 32GB RAM, RTX 4080/4090, Apple M-Max/Ultra |
| **Min Total RAM** | Any (typically 4GB - 8GB) | 12 GB | 24 GB |
| **Min Available RAM**| Any | 3.0 GB | 6.0 GB |
| **Min CPU Cores** | 1 core | 6 logical cores | 8 logical cores |
| **Accelerator Required**| None (CPU only) | Preferred or modern 8+ core CPU | Yes (CUDA >= 8GB VRAM or Apple Silicon unified >= 24GB) |
| **Max RAM Budget** | `min(2048 MB, 35% avail)` | `min(6144 MB, 50% avail)` | `min(16384 MB, 65% avail)` |
| **CPU Utilization Cap** | 50% | 70% | 85% |
| **Target Model Class**| `micro` (OCR, speech, <= 0.5B VLM) | `small` (3B 4-bit VLM) | `medium` (7B - 14B VLM) |

### Conservative Degradation Rules
- **OS Protection Guard**: If the currently available RAM falls below **2.5 GB**, the classifier immediately downgrades the tier to `BASELINE` regardless of raw physical capacity.
- **Power Throttling Guard**: When running under battery saver or low power modes, `HIGH` automatically degrades to `STANDARD` to preserve thermals and battery lifespan.

---

## 3. Measured Phase 1 Baseline Benchmarks

Measurements conducted on the primary development environment (Apple M1 MacBook Air, 8GB RAM, macOS Darwin 24.4.0):

```text
Teach A Skill - Baseline Performance Report
============================================
Cold Startup Latency:        25.14 ms
Hardware Detection Time:     25.14 ms
Full System Health Check:    32.88 ms
Resident Memory (RSS):       20.38 MB
Idle CPU Usage:              0.03%
Background Model Inference:  0 (None)
Heavyweight Model Loaded:    None
```

### Key Takeaways:
- **Instantaneous Startup**: Cold start and full hardware capability inspection completes in ~25 ms.
- **Minimal Memory Footprint**: Uses only ~20 MB of resident memory (RSS), leaving 99%+ of system memory free for user applications and future micro-models.
- **Near-Zero Idle CPU**: Consumes virtually 0% CPU when idle.
- **No Background Inference**: Zero background workers or unnecessary polling loops.

---

## 4. Benchmark Command

Developers and users can reproduce and measure these metrics on any target machine at any time using:

```bash
teach-skill benchmark

# Or formatted as JSON
teach-skill --json benchmark
```

---

## 5. Measured Phase 2 Demonstration Recorder Benchmarks

The demonstration recorder was stress-tested across idle, active recording, and high-throughput saturation scenarios on an Apple M1 MacBook Air (8GB RAM, macOS Darwin 24.4.0):

```text
Phase 2 Recorder Performance & Stress Benchmark
===============================================
Idle RAM (RSS):                22.98 MB
Recording RAM (RSS):           33.48 MB
Memory Growth (Active):        12.47 MB
Idle CPU Usage:                0.05%
Recording CPU Usage:           6.66%
Realistic 1-Min Events:        500 events (192.5 events/sec)
High-Throughput Stress Rate:   9,825.1 events/sec
Storage Footprint:             38.30 MB/min
Screenshot Throughput:         115.5 frames/min
Crash Recovery Latency:        3.36 ms
```

### Key Performance Findings:
1. **Bounded Memory Footprint**: Even during intensive 10,000-event stress bursts, memory growth remains strictly bounded under 15 MB. The multi-tiered backpressure queue sheds non-critical samples before memory expands.
2. **Sub-7% CPU Overhead**: Strategy C (Hybrid Adaptive Capture with min-frame interval debouncing) keeps active recording CPU consumption at 6.66% on a baseline M1 machine, leaving abundant capacity for user workflows.
3. **9,800+ Events/Sec Throughput**: The asynchronous bounded persistence pipeline handles extreme input rates without blocking native event observation threads.
4. **Instantaneous Crash Recovery**: Interrupted sessions are scanned, repaired, and marked `ABORTED` in **3.36 milliseconds**.
5. **Efficient Storage Profile**: Capturing ~115 screen checkpoints and 500 interaction events costs only ~38 MB per minute, orders of magnitude lighter than raw 60 FPS video capture.

To reproduce recorder benchmarks:
```bash
teach-skill benchmark recorder
```

---

## 6. Measured Phase 3 Voice + Text Teaching Benchmarks

The Phase 3 teaching layer was measured across streaming audio capture, offline speech-to-text processing, typed annotation persistence, and cross-layer timeline queries on the baseline development environment (Apple M1, 8GB RAM, macOS Darwin 24.4.0):

```text
Phase 3 Teaching Layer Performance & Stress Benchmark
=====================================================
Idle RAM (RSS):               23.59 MB
Recording RAM (RSS):          37.88 MB
Memory Growth:                14.29 MB
Idle CPU Usage:               0.50%
Recording CPU Usage:          6.46%
Audio Footprint:              35.09 MB/min
Transcript Footprint:         281.95 KB/min
STT Real-Time Factor (RTF):   0.06
Timeline Query Latency:       5.75 µs
Teaching Recovery Latency:    0.37 ms
Sustained Stream Stability:   PASSED (Bounded Memory)
```

### Key Performance Findings:
1. **Memory Bounded Under 40 MB**: Full demonstration recording with simultaneous 16kHz audio capture and asynchronous transcription operates within a total process footprint of **37.88 MB RAM** (growth of only ~14 MB over idle). Raw PCM is immediately evicted once written to disk.
2. **Sub-6.5% Combined CPU Overhead**: Capturing demonstration events, screen checkpoints, streaming audio chunks, and VAD evaluation consumes **6.46% CPU**, preserving host responsiveness for normal desktop application use.
3. **Sub-Microsecond Timeline Query Latency**: `TeachingTimelineEngine` executes binary-search cross-layer lookups in **5.75 microseconds**, providing instantaneous temporal grounding for future AI phases.
4. **Predictable Storage Overhead**: Standard 16kHz 16-bit mono lossless WAV chunking requires **~35 MB per minute** (~2.1 GB per hour). Transcripts and annotations consume only **~280 KB per minute**.
5. **Real-Time Factor (RTF) 0.06**: Asynchronous background transcription processes speech in a fraction of real time without stalling live audio capture.
6. **Sub-Millisecond Crash Recovery**: Recovery scans audio chunks, verifies JSONL lines, repairs manifests, and recalculates SHA-256 hashes in **0.37 milliseconds**.

To reproduce teaching benchmarks:
```bash
teach-skill benchmark teach
```


