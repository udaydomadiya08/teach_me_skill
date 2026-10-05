# Architecture Specification

## 1. Technology Selection & Rationale

Selecting the foundation for a local-first, privacy-first, hardware-adaptive AI skill learning system requires balancing native OS integration, minimal baseline resource consumption, cross-platform maintainability, and seamless future integration with local inference runtimes.

| Candidate Stack | Memory Footprint (Idle) | Startup Latency | Local AI Runtime Compatibility | OS Integration (Input/Screen) | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Python 3.11+ (Standard Library Core)** | **~20 MB** | **< 30 ms** | **Native / First-Class** (llama.cpp, ONNX, MLX, vLLM) | **Excellent** (ctypes, platform APIs) | **SELECTED** |
| Electron + Node.js | 180 - 300 MB | 800 - 1500 ms | Poor (IPC overhead, node bindings) | Medium | Rejected (Bloat) |
| Rust Core + GUI FFI | 10 - 25 MB | < 15 ms | High, but higher maintenance for rapid AI prototyping | High | Reserved for hot paths if needed |
| Go | 25 - 40 MB | < 30 ms | Weak local multimodal ML ecosystem | Medium | Rejected |

### Why Python 3.11+ Standard Library Was Selected:
1. **Zero Runtime Dependencies for Core**: The core Phase 1 foundation runs on Python 3.11+ with zero third-party runtime package dependencies. This guarantees an initial idle memory footprint of **~20 MB**, instantaneous startup (< 30 ms), and absolute protection against supply-chain vulnerabilities or rogue analytics SDKs.
2. **Local AI Ecosystem Standard**: Nearly all state-of-the-art local model runtimes (llama.cpp / `llama-cpp-python`, Apple Silicon MLX, ONNX Runtime, Whisper / faster-whisper) maintain first-class Python bindings with native C-FFI performance.
3. **Deterministic OS Access**: Python provides built-in, low-overhead access to native OS facilities (`ctypes`, `subprocess`, `sysctl`, `/proc`, filesystem APIs).
4. **Clean Abstractions**: Python 3.11 provides modern typing, abstract base classes (`abc.ABC`), frozen dataclasses, structured error handling, and built-in TOML parsing (`tomllib`).

---

## 2. Layered System Architecture

```text
+-------------------------------------------------------------------------------+
|                                  CLI & Tools                                  |
|            (status, hardware, budget, health, benchmark, registry)            |
+-------------------------------------------------------------------------------+
                                        |
+-------------------------------------------------------------------------------+
|                          Application Orchestrator                             |
|              [TeachSkillApp - Coordinates lifecycle and services]             |
+-------------------------------------------------------------------------------+
         |                     |                       |                 |
+-----------------+   +------------------+   +--------------------+  +----------+
|  Configuration  |   | Hardware & Tiers |   |  Model Registry    |  | Privacy  |
|  [ConfigManager]|   | [Detector/Budget]|   | [Descriptor/Match] |  |  Guard   |
+-----------------+   +------------------+   +--------------------+  +----------+
         |                     |                       |                 |
+-------------------------------------------------------------------------------+
|                                Storage Manager                                |
|        [Sandboxed Partitions: config, models, recordings, skills, logs]       |
|               [Atomic file operations, Traversal prevention]                  |
+-------------------------------------------------------------------------------+
                                        |
+-------------------------------------------------------------------------------+
|                           Platform Abstraction Layer                          |
|             +-----------------+---------------+-----------------+             |
|             |  MacOSAdapter   |  LinuxAdapter | WindowsAdapter  |             |
|             +-----------------+---------------+-----------------+             |
+-------------------------------------------------------------------------------+
                                        |
+-------------------------------------------------------------------------------+
|                       Host Operating System & Hardware                        |
|                  (Darwin / Linux / Windows, CPU, RAM, GPU/Metal)              |
+-------------------------------------------------------------------------------+
```

---

## 3. Conceptual Core Interfaces

Phase 1 establishes clean architectural contracts across 17 distinct functional areas. Components planned for future phases are declared as formal abstract contracts and raise `FeatureNotImplementedInPhaseError` if invoked prematurely, preventing false or simulated implementations.

| Interface | Module | Status in Phase 1 | Purpose |
| :--- | :--- | :--- | :--- |
| `IApplication` | `interfaces/application.py` | Implemented | System startup, status query, and graceful shutdown lifecycle. |
| `IPlatformAdapter` | `interfaces/platform.py` | Implemented | OS detection, versioning, desktop environment, and default paths. |
| `IHardwareDetector` | `interfaces/hardware.py` | Implemented | Hardware introspection (CPU, RAM, GPU/Accelerators, storage). |
| `IStorageManager` | `interfaces/storage.py` | Implemented | Sandboxed category routing, atomic read/writes, integrity checks. |
| `IPrivacyPolicy` | `interfaces/privacy.py` | Implemented | Immutable definition of local-only, telemetry, and inference permissions. |
| `IPrivacyGuard` | `interfaces/privacy.py` | Implemented | Runtime barrier enforcing policy and raising `PrivacyViolationError`. |
| `IModelRegistry` | `interfaces/models.py` | Implemented | Model catalog querying, memory compatibility filtering. |
| `IModelProvider` | `interfaces/models.py` | Contract | Abstract runtime provider (llama.cpp, ONNX, MLX). |
| `IEventSystem` | `interfaces/event_system.py`| Contract | Event publisher/subscriber timeline broker (Phase 4). |
| `IRecorder` | `interfaces/recorder.py` | Contract | Universal screen/input demonstration recorder (Phase 2). |
| `IScreenCapture` | `interfaces/screen_capture.py`| Contract | Deterministic OS-level display capture (Phase 2). |
| `IInputCapture` | `interfaces/input_capture.py` | Contract | Deterministic OS-level keyboard and mouse listener hooks (Phase 2). |
| `IWindowManager` | `interfaces/window_manager.py`| Contract | Deterministic active window and process identifier (Phase 2). |
| `ISpeechEngine` | `interfaces/speech.py` | Contract | Local audio speech-to-text transcription engine (Phase 3). |
| `IVisionEngine` | `interfaces/vision.py` | Contract | Local UI element detection and visual bounding (Phase 5/6). |
| `IOCREngine` | `interfaces/ocr.py` | Contract | Local optical character recognition engine (Phase 5). |
| `ISkill` | `interfaces/skills.py` | Contract | Executable learned skill definition (Phase 8). |
| `ISkillStore` | `interfaces/skills.py` | Contract | Local skill persistence and retrieval store (Phase 9). |
| `IExecutor` | `interfaces/executor.py` | Contract | Deterministic execution engine for learned skills (Phase 10). |
| `IVerifier` | `interfaces/verifier.py` | Contract | State transition verification and deviation detector (Phase 11). |

---

## 4. Hardware Detection & Adaptive Budgeting

### Hardware Introspection
The `HardwareDetector` collects hardware capabilities across:
- **CPU**: Architecture (`arm64`, `x86_64`), vendor, processor string, logical cores, physical cores, vector capabilities (`neon`, `avx2`, `fma`).
- **Memory**: Total physical RAM and available unallocated RAM (queried via `sysctl` on macOS, `/proc/meminfo` on Linux, and `GlobalMemoryStatusEx` on Windows).
- **GPU / Acceleration**: Detects Apple Silicon unified memory GPUs (Metal), NVIDIA GPUs (CUDA via `nvidia-smi`), and AMD accelerators (ROCm via `rocm-smi`). Integrated or CPU-only setups fall back to `none` without error.
- **Storage**: Volume total and free capacity via `shutil.disk_usage`.

### Deterministic, Conservative Performance Tiers
Classification evaluates multiple hardware dimensions and degrades safely when constrained:

1. **`BASELINE`**:
   - Modest laptops, machines with <= 8 GB RAM, or CPU-only machines.
   - Low-power budget: max memory capped at <= 2048 MB (or 35% of available RAM). CPU ceiling 50%.
   - Target model class: `micro` (e.g. compact OCR, tiny speech model, <= 0.5B VLM).
2. **`STANDARD`**:
   - Modern laptops with >= 12 GB RAM, >= 6 CPU cores, and >= 3 GB available RAM with hardware acceleration (or modern >= 8-core CPU).
   - Memory budget capped at <= 6144 MB (50% of available RAM). CPU ceiling 70%.
   - Target model class: `small` (e.g. 3B 4-bit quantized VLM).
3. **`HIGH`**:
   - Workstations with >= 24 GB RAM, >= 8 cores, >= 6 GB free RAM, and high-performance acceleration (Apple Silicon unified >= 24 GB or NVIDIA CUDA >= 8 GB VRAM).
   - Memory budget capped at <= 16384 MB (65% of available RAM). CPU ceiling 85%.
   - Target model class: `medium` (e.g. 7B - 14B VLM).
4. **Safety Overrides**:
   - If available memory drops below **2.5 GB**, the classifier automatically downgrades to **`BASELINE`**, ensuring the host OS is never starved.
   - If battery saver / low power mode is active, `HIGH` degrades to `STANDARD` to preserve thermals and battery.

---

## 5. Storage Architecture

Local storage is sandboxed into dedicated partitions under a root directory (e.g. `~/Library/Application Support/TeachASkill` on macOS, `~/.local/share/teach_a_skill` on Linux, `%LOCALAPPDATA%/TeachASkill` on Windows):

```text
<base_dir>/
├── config/       # Application configuration and user preferences
├── models/       # Local model descriptors and future weights
├── recordings/   # Raw demonstration recordings and capture sessions
├── skills/       # Compiled executable skills and metadata
├── sessions/     # Active and past teaching sessions
├── logs/         # Structured, privacy-safe application logs
└── cache/        # Temporary working buffers
```

### Atomic File Operations
All file writes are performed atomically:
1. Data is written to a temporary file in the identical destination directory.
2. The file descriptor is flushed and synchronized to persistent storage via `os.fsync()`.
3. The temporary file replaces the target via `Path.replace()`, guaranteeing POSIX atomicity and preventing file corruption during power loss or abrupt process termination.

### Path Traversal Defense
`StorageManager.get_path()` resolves canonical paths and validates that candidate targets remain strictly within the designated category root, preventing directory traversal exploits (e.g. `../../etc/passwd`).

---

## 6. Model Registry Architecture

The `ModelRegistry` maintains declarative specifications (`ModelDescriptor`) without downloading weights or requiring active model files at launch.

Each descriptor records:
- Modalities (`TEXT`, `VISION`, `SPEECH`, `OCR`, `MULTIMODAL`)
- Parameter count and quantization scheme (`q4_k_m`, `int8`, `f16`)
- Exact memory requirements in megabytes
- CPU, GPU, and OS compatibility flags
- Capability tags

When an operation requests a model, `find_compatible_models(budget)` matches candidates against the host's actual memory ceiling and accelerator availability. If a model exceeds the machine's budget, it is safely excluded from selection.

---

## 7. Demonstration Recorder Subsystem (Phase 2)

```text
+-----------------------------------------------------------------------------------------+
|                                    UniversalRecorder                                    |
|   +---------------------------------------------------------------------------------+   |
|   |                           Event Ingestion & Routing                             |   |
|   +---------------------------------------------------------------------------------+   |
|            |                         |                          |                       |
|   +-----------------+       +-------------------+       +-----------------+             |
|   | Movement        |       | Shortcut          |       | PrivacyFilter   |             |
|   | Coalescer       |       | Reconstructor     |       | (Record/Mask/   |             |
|   | (Sub-pixel &    |       | (Combines mods &  |       |  Suppress)      |             |
|   |  drag curve)    |       |  keys: Cmd+C)     |       |                 |             |
|   +-----------------+       +-------------------+       +-----------------+             |
|            \                         |                         /                        |
|             \                        |                        /                         |
|   +---------------------------------------------------------------------------------+   |
|   |              BoundedEventQueue (Capacity: 10,000, Multi-tier Backpressure)      |   |
|   |      [Sheds LOW @ 80% (frames)] -> [Sheds MEDIUM @ 90% (moves)] -> [CRITICAL]   |   |
|   +---------------------------------------------------------------------------------+   |
|                                              |                                          |
|                                   AsyncPersistenceWorker                                |
|                                              |                                          |
|                                       SessionStorage                                    |
|             +-----------------+--------------+------------------+                       |
|             |                 |                                 |                       |
|       events.jsonl      frames/*.png                     metadata/*.json                |
|       (Incremental      (Atomic raster checkpoint        (summary.json,                 |
|        streaming)        persisted with event linkage)    frame_index.json)             |
+-----------------------------------------------------------------------------------------+
```

### Component Roles
1. **`UniversalRecorder`**: Central coordinator managing lifecycle transitions (`CREATED` -> `RECORDING` <-> `PAUSED` -> `STOPPING` -> `COMPLETED`/`ABORTED`), event sequencing, and frame triggers.
2. **`MovementCoalescer`**: Trajectory-preserving mouse optimizer. Filters redundant stationary jitter while preserving drag curves and inflection points (> 20 degree angle deviations).
3. **`ShortcutReconstructor`**: Aggregates modifier keys (`CMD`, `CTRL`, `ALT`, `SHIFT`) and physical keystrokes into canonical shortcut representations.
4. **`PrivacyFilter`**: Intercepts raw input events and window focus changes. Enforces `RECORD`, `MASK`, or `SUPPRESS` policies, blocks recording on excluded applications (e.g. password managers, banking apps), and matches sensitive window title regexes.
5. **`FrameIndexer`**: Maintains a bidirectional temporal index mapping events to nearest preceding/succeeding screen frames for rapid retrieval by future AI models.
6. **`BoundedEventQueue`**: Thread-safe bounded buffer decoupling native OS hook threads from disk I/O.
7. **`AsyncPersistenceWorker`**: Daemon background thread draining the queue and streaming events to disk without blocking the main event loops.

---

## 8. Screen Capture Strategy Evaluation & Decision

Before implementing screen capture, three candidate strategies were evaluated against the project's low-hardware mandate:

| Metric | Strategy A: Continuous Video (e.g. 30/60 FPS H.264/WebM) | Strategy B: Pure Event-Triggered Screenshots | Strategy C: Hybrid Adaptive Capture (Event + Sparse Heartbeat) |
| :--- | :--- | :--- | :--- |
| **CPU Overhead** | Very High (15% - 40% CPU encoding) | **Very Low (< 2% CPU)** | **Low (3% - 7% CPU)** |
| **Storage Usage** | Very High (~150 - 400 MB/min) | **Very Low (~5 - 15 MB/min)** | **Low to Moderate (~20 - 45 MB/min)** |
| **Semantic Usefulness** | High, but contains massive redundancy | High for input, misses passive UI updates (e.g. loading bars) | **Optimal (Captures all user actions + passive changes)** |
| **Weak Machine Usability**| Poor (Causes thermal throttling and frame drops on 8GB machines) | Excellent | **Excellent (Hardware-adaptive frequency)** |
| **Decision** | **REJECTED (Bloat & Overhead)** | **REJECTED (Misses passive UI transitions)** | **SELECTED (Optimal Balance)** |

### Strategy C Architecture
Strategy C was selected and implemented:
- **Event-Driven Checkpoints**: Immediate screenshot captured upon `session_start`, `mouse_click`, `mouse_drag` termination, `window_focus_changed`, and `session_stop`.
- **Hardware-Adaptive Heartbeat**:
  - `BASELINE`: Minimal event-driven capture only (0 Hz periodic heartbeat).
  - `STANDARD`: Balanced event-driven capture + 0.33 Hz (3-second) periodic heartbeat.
  - `HIGH`: Rich event-driven capture + 1.0 Hz (1-second) periodic heartbeat.
- **Debounce Guard**: Sub-second input clustering (e.g. rapid double-clicks) is debounced to a configurable minimum frame interval (default: 250 ms) to prevent disk and encoder thrashing.
- **Image Format**: PNG format encoded via a zero-dependency pure Python stdlib encoder (`zlib`), ensuring zero external C-library bloat, lossless quality for UI text/OCR, and universal compatibility.

---

## 9. Session Storage Layout & Crash Resilience

Demonstration sessions are stored under `<base_dir>/recordings/<session_id>/`:

```text
recordings/<session_id>/
├── manifest.json         # Session metadata, hardware profile, status, event distributions
├── checksums.json        # SHA-256 integrity hashes for events and manifest
├── events/
│   └── events.jsonl      # Streaming append-only JSONL raw events (immediately flushed)
├── frames/
│   ├── frame_0001.png    # Screen checkpoint raster files
│   └── frame_0002.png
└── metadata/
    ├── summary.json      # Factual, non-AI deterministic statistical summary
    └── frame_index.json  # Temporal index linking event IDs to frame IDs
```

### Crash Recovery Mechanism
If the process is ungracefully terminated (power loss, OS SIGKILL, crash):
1. `SessionStorage.recover_session(storage_manager, session_id)` scans the directory.
2. It parses all persisted events in `events.jsonl` up to the point of interruption.
3. If no `SESSION_STOPPED` event is found, it automatically marks the session status as **`ABORTED`** (preventing incomplete recordings from being mistaken for completed demonstrations).
4. Reconstructs event count and type distributions and updates the manifest.
5. Generates integrity checksums and finalizes recovery.

---

## 11. Phase 5: Local UI Perception & OCR Subsystem

Phase 5 introduces deterministic, lightweight local perception over captured screen evidence.

```text
recording/
├── raw/                # Immutable Phase 2 events & frames
├── events/             # Immutable Phase 2 event stream
├── metadata/           # Immutable Phase 2 session summaries
├── teaching/           # Immutable Phase 3 voice, transcripts, annotations
├── representation/     # Immutable Phase 4 canonical timeline
└── perception/         # Phase 5 isolated perception partition
    ├── manifest.json
    ├── frames.jsonl
    ├── elements.jsonl
    ├── text_regions.jsonl
    ├── ocr_results.jsonl
    ├── indexes/
    │   └── perception_index.json
    └── checksums.json
```

### Architectural Boundary: "What Is Visibly Present", NOT "What It Means"
- **Permitted**: Edge & contour geometric detection, local OCR, normalized coordinates, spatial reading order, containment fusion, deterministic caching, structural queries.
- **Strictly Prohibited**: Goal inference, task classification, user intent guessing, executable code generation, UI automation, action recommendation, LLM/remote API dependencies.

### OCR Provider Abstraction
- **`AppleVisionOCRProvider`**: Hardware-accelerated native macOS `VNRecognizeTextRequest` utilizing Neural Engine / GPU with zero external network access.
- **`TesseractOCRProvider`**: Local open-source OCR engine using `/opt/homebrew/bin/tesseract` or system binary.
- **`MockOCRProvider`**: Deterministic synthetic provider for testing and reproducible benchmarking.

### UI Element Detection & Platform Accessibility
- **`GeometryDetector`**: Visual-only detector using OpenCV contour analysis and geometric heuristics. Classifies neutral structural types: `BUTTON_LIKE`, `INPUT_LIKE`, `CHECKBOX_LIKE`, `PANEL`, `WINDOW_REGION`, `UNKNOWN_REGION`.
- **`PlatformAccessibilityDetector`**: Native macOS Accessibility API (`ApplicationServices` / `AXUIElement`) inspection. Operates with graceful degradation: if permission is unavailable, mode falls back immediately to `SCREEN_ONLY` without errors.

### Deterministic Spatial Reading Order
- Sorts text regions and UI elements top-to-bottom, left-to-right using quantized vertical baseline tolerance bands (`12px` default) to prevent vertical jitter from re-ordering inline elements.
- Stable tie-breaking via element/region IDs.

### Multi-Source Spatial Fusion
- Associative spatial containment: merges OCR text into containing geometric/accessibility bounding boxes without semantic interpretation.
- Maintains provenance sources: `["IMAGE", "OCR"]` or `["ACCESSIBILITY", "OCR"]`.

### Coordinate Normalization & Retina Scaling
- `CoordinateTransformer` unifies screen point space, frame pixel space (device pixels), and normalized `[0, 1]` coordinates.
- Handles Retina high-DPI scaling (2.0x, 3.0x) and origin translations deterministically.

### Cache & Storage Engine
- **Atomic Promotion**: Outputs are staged in `.perception_staging` and atomically swapped to `perception/` upon successful completion.
- **Content-Keyed Cache**: Cache key is derived from `SHA-256(frame_bytes) + provider_id + provider_version + detector_id + config_hash`. Identical frames with identical settings execute at >1500 fps.

