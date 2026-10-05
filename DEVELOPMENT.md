# Development Guide

This guide describes how to develop, test, and maintain the Teach A Skill codebase.

---

## 1. Environment Setup

### Requirements
- Python 3.11 or later
- Recommended: [`uv`](https://github.com/astral-sh/uv) (fast Python package manager)
- Git

### Initializing the Workspace
```bash
# Clone the repository
git clone https://github.com/example/teach_a_skill.git
cd teach_a_skill

# Create virtual environment
uv venv --python 3.11 .venv
source .venv/bin/activate

# Install in editable mode with development dependencies
uv pip install -e ".[dev]"
```

---

## 2. Running Automated Tests

All tests are located in `tests/` and execute via `pytest`.

```bash
# Run entire test suite
./scripts/test.sh

# Or directly with pytest
pytest -v

# Run a specific test file
pytest -v tests/test_tiers.py

# Run with keyword filter
pytest -v -k "privacy"
```

The test suite covers:
- Hardware detection (CPU, RAM, GPU, OS, storage) and graceful error handling.
- Deterministic tier classification across simulated profiles (weak CPU, 8GB laptop, 16GB laptop, 32GB machine, GPU workstation, Apple Silicon).
- Adaptive resource budgeting and memory allocation constraints.
- Configuration loading, validation, saving, and schema migrations.
- Privacy guard enforcement (blocking network, telemetry, and unpermitted capture).
- Storage sandboxing, path traversal attack prevention, and atomic file replacement.
- Zero-model startup and graceful degradation when GPU is absent.
- Privacy-safe logging with sensitive field redaction.

---

## 3. Code Style & Static Analysis

We enforce strict formatting and linting using `ruff`.

```bash
# Run linting and formatting verification
./scripts/lint.sh

# Automatically fix lint issues and reformat
ruff check --fix .
ruff format .
```

Configuration is defined in `pyproject.toml`:
- Line length: 100 characters
- Python target: 3.11+
- Linters enabled: `E`, `F`, `W`, `I` (isort), `B` (flake8-bugbear), `C4` (flake8-comprehensions)

---

## 4. Using the Developer CLI

The package provides the `teach-skill` CLI entrypoint (as well as `python -m teach_a_skill`):

```bash
# General status
teach-skill status

# Detailed hardware detection
teach-skill hardware

# Adaptive memory/CPU budget
teach-skill budget

# System health diagnostics (exit code 0 if healthy, 1 if unhealthy)
teach-skill health

# Baseline startup latency and memory footprint
teach-skill benchmark

# Model registry and budget compatibility
teach-skill registry

# Export active configuration
teach-skill config

# All commands support machine-readable JSON output
teach-skill --json health
teach-skill --json hardware
```

---

## 5. Repository Layout

```text
teach_a_skill/
├── pyproject.toml             # Build system, metadata, and tool configuration
├── README.md                  # Project overview and quick start
├── ARCHITECTURE.md            # Detailed architecture specification
├── DEVELOPMENT.md             # Development and testing documentation
├── PRIVACY.md                 # Privacy guarantees and enforcement
├── SECURITY.md                # Security and sandboxing policies
├── PERFORMANCE.md             # Low-hardware baseline and benchmarks
├── ROADMAP.md                 # 15-phase implementation plan
├── scripts/                   # Developer automation scripts
│   ├── dev.sh
│   ├── test.sh
│   ├── lint.sh
│   └── benchmark.sh
├── src/teach_a_skill/
│   ├── __init__.py            # Package root and version
│   ├── __main__.py            # Entry point for python -m teach_a_skill
│   ├── app.py                 # Application lifecycle orchestrator
│   ├── cli/                   # Developer CLI implementation
│   │   ├── __init__.py
│   │   └── main.py
│   ├── core/                  # Errors, logging, and health check services
│   │   ├── __init__.py
│   │   ├── errors.py
│   │   ├── logging.py
│   │   └── health.py
│   ├── interfaces/            # Conceptual contracts for all 17 components
│   │   ├── __init__.py
│   │   ├── application.py
│   │   ├── platform.py
│   │   ├── hardware.py
│   │   ├── storage.py
│   │   ├── privacy.py
│   │   ├── event_system.py
│   │   ├── recorder.py
│   │   ├── screen_capture.py
│   │   ├── input_capture.py
│   │   ├── window_manager.py
│   │   ├── speech.py
│   │   ├── vision.py
│   │   ├── ocr.py
│   │   ├── models.py
│   │   ├── skills.py
│   │   ├── executor.py
│   │   └── verifier.py
│   ├── hardware/              # Hardware detector, profile, tiers, budget, benchmark
│   │   ├── __init__.py
│   │   ├── detector.py
│   │   ├── profile.py
│   │   ├── tiers.py
│   │   ├── budget.py
│   │   └── benchmark.py
│   ├── platform/              # OS platform adapters (macOS, Linux, Windows)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── macos.py
│   │   ├── linux.py
│   │   └── windows.py
│   ├── privacy/               # Policy dataclass and PrivacyGuard
│   │   ├── __init__.py
│   │   ├── policy.py
│   │   └── guard.py
│   ├── config/                # Schema, defaults, and ConfigManager
│   │   ├── __init__.py
│   │   ├── schema.py
│   │   ├── defaults.py
│   │   └── manager.py
│   ├── storage/               # Local directory sandbox and atomic file operations
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   └── atomic.py
│   └── models/                # Model descriptor and ModelRegistry
│       ├── __init__.py
│       ├── descriptor.py
│       └── registry.py
└── tests/                     # Comprehensive automated test suite
```

---

## 6. Guidelines for Later Phases

1. **Do not bypass `PrivacyGuard`**: Any new subsystem that handles file writes, device capture, or future networking MUST verify with `PrivacyGuard`.
2. **Do not perform direct raw file writes**: Always use `StorageManager` to obtain sandboxed paths and utilize atomic writing (`write_atomic_text` / `write_atomic_bytes`) to prevent corruption.
3. **Respect `ResourceBudget`**: Before initializing or loading models in Phase 6+, consult `app.get_resource_budget()` to verify memory and device compatibility.
4. **Never log sensitive data**: Use the privacy-safe logger from `teach_a_skill.core.logging`. Never pass raw passwords, auth tokens, unredacted keystrokes, or raw audio frames into standard log messages.
