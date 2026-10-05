# Teach A Skill

A **local-first, privacy-first, hardware-adaptive AI skill-learning system**.

The eventual product enables users to teach an AI computer tasks through screen demonstration, mouse actions, keyboard inputs, window context, and voice/text explanations, turning demonstrations into reusable, executable skills.

> **CURRENT STATUS: PHASE 9 — SKILL FORMAT, MEMORY & VERSIONING COMPLETED**
> This repository contains the complete **Phase 1 Foundation**, **Phase 2 Universal Demonstration Recorder**, **Phase 3 Local Voice + Text Teaching Layer**, **Phase 4 Canonical Representation**, **Phase 5 Local UI Perception & OCR**, **Phase 6 Multimodal Intelligence Layer**, **Phase 7 Intent & Demonstration Understanding Layer**, **Phase 8 Skill Compiler**, and **Phase 9 Skill Format, Memory & Versioning**. Phase 9 persists, versions, indexes, and compares skills with full demonstration lineage without executing, replaying, or controlling the user interface. Execution belongs strictly to Phase 10+.

---

## Non-Negotiable Core Principles

1. **Local-First**: All storage, configuration, telemetry-free logs, and transcription operate exclusively on the local machine. Zero cloud speech APIs, zero remote LLM inference, zero network transmission.
2. **Privacy-First**: User demonstrations involve sensitive personal data (screens, keystrokes, voice, application state). By default:
   - Network access: **DENIED**
   - Telemetry / Analytics: **DISABLED**
   - Cloud Inference: **DISABLED**
   - Data Upload: **DISABLED**
   - Sensitive input policies: Configurable (`RECORD`, `MASK`, `SUPPRESS`) with automatic application/window exclusions.
   - Microphone capture: Explicit user initiation only, prominent visual state indicator (`MIC: RECORDING / PAUSED / STOPPED`), immediate hardware release on pause/stop.
3. **Low-Hardware Baseline**: Built to remain fully operational and useful on modest laptops (e.g. 8GB RAM, CPU-only). Does NOT require a dedicated GPU or high VRAM merely to launch, record, or teach.
4. **Hardware-Adaptive Architecture**: Deterministically identifies host hardware and scales across three tiers (`BASELINE`, `STANDARD`, `HIGH`), computing a strict `ResourceBudget` that prevents system starvation or out-of-memory crashes.
5. **Deterministic Core, AI Only Where Needed**: Mouse, keyboard, screen capture, window tracking, storage, audio streaming, VAD, and event clocks are handled strictly by deterministic OS APIs.
6. **Cross-Platform**: Clean abstraction boundaries for macOS, Linux, and Windows from day one.
7. **Never Lose Raw Trace (Immutable Evidence)**: High-frequency raw physical demonstration events (`events.jsonl`, `frames/`) are strictly immutable. Teaching evidence (`teaching/audio/`, `transcript.jsonl`, `annotations.jsonl`, `corrections.jsonl`) lives in an independent layer referenced by session ID.

---

## Implemented Architecture

### Phase 1 Foundation
- **Hardware Capability Detector**: Deep queries for CPU cores, RAM, GPU/accelerators, thermal states, and storage volumes.
- **Conservative Tier Classifier**: Classifies hosts into `BASELINE`, `STANDARD`, or `HIGH` with conservative degradation guards.
- **Adaptive Resource Budget**: Memory ceilings and CPU caps preventing host OS starvation.
- **Model Registry Catalog**: Zero-model declarative registry matching models to available hardware.
- **Sandboxed Local Storage**: Structured category partitions, path traversal guards, atomic file replacement.
- **Privacy Policy & Runtime Guard**: `PrivacyGuard` raising `PrivacyViolationError` on network or telemetry attempts.

### Phase 2 Universal Demonstration Recorder
- **First-Class RecordingSession**: Formal state machine (`CREATED`, `RECORDING`, `PAUSED`, `STOPPING`, `COMPLETED`, `ABORTED`, `FAILED`).
- **Unified Event Timeline**: Dual-timestamped events (UTC ISO8601 wall clock + high-resolution monotonic clock) with monotonic sequence numbers.
- **Movement Coalescing Engine**: Sub-pixel jitter filter and inflection angle detection preserving drag trajectories while preventing event flood.
- **Keyboard & Shortcut Capture**: Key down/up, modifier tracking, combination reconstruction (`Cmd+C`, `Ctrl+Shift+P`).
- **Sensitive Input Protection**: `PrivacyFilter` supporting `RECORD`, `MASK`, and `SUPPRESS` policies, application-level exclusion (e.g., 1Password, Bitwarden), and window title regular expressions.
- **Hybrid Adaptive Screen Capture (Strategy C)**: Event-triggered snapshots (clicks, drags, window focus) plus sparse periodic checkpoints (3s on BALANCED, 1s on HIGH, none on MINIMAL). Built-in pure stdlib PNG encoder.
- **Bidirectional Temporal Frame Indexing**: Rapid temporal lookups associating screenshots with triggering events and prior/subsequent actions.
- **Bounded Buffer & Backpressure Worker**: Memory-bounded event queue (10,000 capacity) shedding LOW priority (screenshots) at 80% and MEDIUM priority (dense moves) at 90%, while strictly preserving CRITICAL input events.
- **Crash-Resilient Storage Format**: Streaming `events.jsonl` writes, partitioned `frames/` and `metadata/` directories, SHA-256 checksums, and crash recovery marking interrupted sessions as `ABORTED`.
- **Synthetic Event Engine**: Deterministic testing and stress evaluation without requiring active OS desktop hooks.
- **Deterministic Non-AI Demonstration Summary**: Real-time statistical summary (duration, event counts, application context, screenshot statistics).

### Phase 3 Local Voice + Text Teaching Layer
- **Audio Capture Subsystem**: Streaming 16kHz 16-bit mono PCM capture, atomic WAV chunk writer with SHA-256 integrity, bounded memory buffer (raw PCM evicted after write), zero full-session in-memory audio.
- **Microphone Discovery & Permission Manager**: Hardware abstraction detecting macOS (CoreAudio/ffmpeg), Linux (ALSA/PulseAudio/parecord), and Windows (DirectShow/WASAPI) with graceful degradation to text teaching if unavailable.
- **Local Speech-to-Text Abstraction**: `ISpeechToTextProvider` architecture supporting `LocalWhisperSTTProvider` (CPU/accelerator binaries, offline-first) and deterministic `MockSTTProvider` for CI and testing.
- **Energy-Based VAD**: Pure standard-library RMS energy voice activity detector identifying speech intervals with zero ML dependencies.
- **Asynchronous Transcription Queue**: Priority decoupled from capture (`RAW AUDIO > STT`), tracking queue backlog, processing latency, and real-time factor (RTF).
- **Text Teaching & Annotation Subsystem**: Direct typed teaching annotations (`instruction`, `explanation`, `warning`, `context`, `correction`, `note`, `goal_hint`) referencing specific event IDs, time intervals, or frames.
- **Non-Destructive Revisioning & Transcript Editor**: Append-only JSONL with soft-deletion, segment splitting, segment merging, and complete audit logging in `corrections.jsonl`.
- **Teaching Timeline Engine**: Sub-microsecond binary-search temporal fusion engine querying synchronized demonstration state:
  - What was said during this mouse click? (`get_speech_for_event`)
  - What events occurred while speaking this sentence? (`get_events_for_speech_segment`)
  - What text annotations reference this action? (`get_annotations_for_event`)
  - Cross-layer snapshot context (+/- window_ns) (`get_context_at`)
- **Strict Evidence Immutability**: Phase 2 raw evidence files (`events.jsonl`, `frames/`, `manifest.json`, `checksums.json`) are strictly preserved and never mutated when transcripts or annotations are edited.
- **Crash Recovery & Integrity**: Reconstructs teaching manifests, cleans up partial `.tmp` audio chunks, and re-computes SHA-256 checksums on startup.

---

## Quick Start

### Prerequisites
- Python 3.11 or later
- Recommended: [`uv`](https://github.com/astral-sh/uv) or standard Python virtual environment

### Installation
```bash
# Clone the repository
git clone https://github.com/example/teach_a_skill.git
cd teach_a_skill

# Create virtual environment and install in editable mode
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Running the CLI

```bash
# Show system overview, hardware tier, budget, and privacy state
teach-skill status

# Detailed hardware detection metrics
teach-skill hardware

# Run full system health checks
teach-skill health

# Run Phase 1 baseline startup & hardware benchmarks
teach-skill benchmark

# Run Phase 2 recorder stress & performance benchmarks
teach-skill benchmark recorder

# Run Phase 3 teaching layer stress & footprint benchmarks
teach-skill benchmark teach

# Discover microphones and permissions
teach-skill audio devices

# Start simultaneous teaching alongside demonstration recording
teach-skill teach start --session-id <session_id>

# Pause / Resume voice capture
teach-skill teach pause
teach-skill teach resume

# Add text teaching annotation attached to timeline & event ID
teach-skill teach annotate "This button submits the transaction" --type instruction --event evt_001

# Inspect and non-destructively edit transcripts
teach-skill teach transcript list --session-id <session_id>
teach-skill teach transcript edit --session-id <session_id> --segment-id seg_000001 --text "Corrected spoken sentence"

# Query unified cross-layer timeline at timestamp
teach-skill teach timeline <session_id> --timestamp-ns 1000000000

# Stop teaching and finalize transcripts and checksums
teach-skill teach stop
```

### Running Tests & Quality Checks
```bash
# Run all 124 automated tests across Phase 1, Phase 2, and Phase 3
./scripts/test.sh

# Run static analysis and formatting checks
./scripts/lint.sh

# Run performance benchmarks
./scripts/benchmark.sh
```

---

## Documentation Index

- [ARCHITECTURE.md](ARCHITECTURE.md) - Layered system design, recorder subsystem, and strategy decisions.
- [DEVELOPMENT.md](DEVELOPMENT.md) - Developer setup, testing guidelines, and extension workflows.
- [PRIVACY.md](PRIVACY.md) - Strict local-only privacy guarantees, sensitive input filters, and exclusions.
- [SECURITY.md](SECURITY.md) - Threat modeling, input validation, and sandbox isolation.
- [PERFORMANCE.md](PERFORMANCE.md) - Low-hardware baseline, tier classification, and measured benchmarks.
- [ROADMAP.md](ROADMAP.md) - 15-phase implementation trajectory from foundation to production.
- [docs/phase7_intent.md](docs/phase7_intent.md) - Phase 7 Intent & Demonstration Understanding specification and user guide.
- [docs/phase8_skill_compiler.md](docs/phase8_skill_compiler.md) - Phase 8 Skill Compiler specification, Skill IR schema, and CLI guide.
- [docs/phase9_skill_memory.md](docs/phase9_skill_memory.md) - Phase 9 Skill Format, Memory & Versioning specification and user guide.
- [docs/phase14_security_hardening.md](docs/phase14_security_hardening.md) - Phase 14 Privacy, Security Hardening & Cross-Platform Packaging specification and user guide.
- [docs/phase15_production_release.md](docs/phase15_production_release.md) - Phase 15 Production Release, Final Benchmarking & Verification specification.
