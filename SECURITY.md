# Security Policy & Safeguards

This document outlines the security architecture and defensive controls implemented in Phase 1 of Teach A Skill.

---

## 1. Threat Modeling for Local Skill Learning

Teaching an AI system to automate desktop tasks creates unique security considerations:
- **Path Traversal Attacks**: Malicious skill files or crafted filenames attempting to overwrite sensitive system files (e.g. `~/.ssh/authorized_keys`, `/etc/passwd`).
- **Unsafe Deserialization**: Arbitrary code execution via unsafe serialization libraries like `pickle`.
- **Command Injection**: Unsanitized subprocess arguments in platform detection or system commands.
- **Model Poisoning / Supply Chain Attacks**: Unauthorized automatic downloading of weights from unverified remote endpoints.
- **Credential Storage**: Accidental plaintext logging or insecure caching of user credentials during demonstration.

---

## 2. Implemented Defensive Controls

### A. Path Traversal Protection
All filesystem operations are routed through `StorageManager.get_path()`.
- Paths are resolved to canonical form using `Path.resolve()`.
- The candidate path is verified against the partition category root using `Path.relative_to()`.
- Any attempt to escape the designated sandbox raises `StoragePathTraversalError`.

### B. Safe Deserialization
- No use of Python `pickle` or `marshal` anywhere in the codebase.
- Configuration and metadata parsing uses standard, safe parsers:
  - `json` for structured data and metadata.
  - Python 3.11's built-in `tomllib` (read-only, memory-safe parser) for TOML configuration.

### C. Shell Injection Prevention
- All internal system calls in `HardwareDetector` use strict `list` argument vectors (e.g. `["sysctl", "-n", "machdep.cpu.brand_string"]`).
- No calls use `shell=True`, eliminating shell command injection risks.

### D. Model Supply Chain Safeguards
- In Phase 1, **no models are downloaded or executed**.
- Future phases will enforce cryptographic hash verification (SHA-256) on any local model weights before loading into memory.
- No automatic downloading of executable scripts or unverified third-party binaries.

### E. Configuration Input Validation
`ConfigManager.validate()` enforces strict value constraints:
- Log levels must match approved enum values (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- Performance tier overrides must match defined tiers (`BASELINE`, `STANDARD`, `HIGH`).
- Recording FPS is bounded between 1 and 60.
- Retention periods are validated to prevent negative or infinite unbounded retention.

---

## 3. Vulnerability Reporting

To report a vulnerability or privacy boundary flaw, open an issue labeled `security` or contact the maintainers locally. All reports are treated with high priority.
