# Phase 14 — Privacy, Security Hardening & Cross-Platform Packaging

## 1. Overview & Architecture

Phase 14 transitions **Teach A Skill** from a development and learning system into a hardened, secure, tamper-evident, privacy-preserving, and cross-platform deployable application.

```text
CORE ENGINE (Platform-Independent, Local-First)
     │
     ├── PRIVACY LAYER (PrivacyAuditor, Redaction, Export, Deletion)
     ├── SECURITY LAYER (SecretDetector, NetworkIsolationMonitor, DependencyAuditor)
     ├── STORAGE SECURITY (StorageSecurityManager, Canonical Paths, Symlink Defenses)
     ├── AUDIT INTEGRITY (AuditIntegrityManager, SHA-256 Chained Hash Log)
     ├── PERMISSION MANAGER (Least Privilege, NETWORK=DENIED default)
     └── PLATFORM ABSTRACTION (PlatformManager, PlatformAdapter)
              │
       ┌──────┼──────┐
       ↓      ↓      ↓
    macOS   Linux  Windows
    (Real)  (Sim)  (Sim)
```

## 2. Absolute Guarantees

- **Local-Only & Offline**: Network permissions default to `DENIED`. Zero unexpected outbound sockets or cloud dependencies.
- **Fail-Closed Permissions**: Explicit permissions required for screen recording, microphone, accessibility, and input control.
- **Data Minimization & Redaction**: Secrets (AWS, GitHub, Stripe, DB credentials, Private Keys) are stripped and redacted before persistence.
- **Filesystem Security**: Null byte injection, path traversal (`../../etc/passwd`, `..\..\Windows\System32`), and symlink escapes are strictly blocked.
- **Audit Integrity**: Cryptographic chained hash records. Any tampering, reordering, deletion, or truncation halts operations in `SECURITY_INCIDENT` state.
- **Cross-Platform**: Unified `PlatformCapabilities` matrix across macOS, Linux (X11 & Wayland), and Windows (UI Automation, DPAPI).

## 3. Platform Capabilities Matrix

| Capability | macOS (Real) | Linux (Simulated) | Windows (Simulated) |
|---|---|---|---|
| Screen Capture | `SUPPORTED_WITH_PERMISSION` | `SUPPORTED_WITH_PERMISSION` / `DEGRADED` (Wayland) | `SUPPORTED_WITH_PERMISSION` |
| Mouse & Keyboard Input | `SUPPORTED_WITH_PERMISSION` | `SUPPORTED_WITH_PERMISSION` | `SUPPORTED` |
| Accessibility | `SUPPORTED_WITH_PERMISSION` | `SUPPORTED_WITH_PERMISSION` (AT-SPI) | `SUPPORTED` (UI Automation) |
| Audio Capture | `SUPPORTED_WITH_PERMISSION` | `SUPPORTED_WITH_PERMISSION` (ALSA/Pulse) | `SUPPORTED_WITH_PERMISSION` (WASAPI) |
| Model Acceleration | `SUPPORTED` (Metal / Apple Silicon) | `SUPPORTED` (ROCm / CUDA / CPU) | `SUPPORTED` (DirectML / CPU) |
| Secure Storage | `SUPPORTED` (Keychain) | `SUPPORTED` (SecretService / Libsecret) | `SUPPORTED` (DPAPI) |
| Process Control | `SUPPORTED` | `SUPPORTED` | `SUPPORTED` |

## 4. CLI Commands Added in Phase 14

### Security Subsystem
```bash
teach-skill security health          # Check security layer health
teach-skill security audit           # View tamper-evident audit report
teach-skill security dependencies    # Audit dependencies and license compliance
teach-skill security permissions     # Audit canonical permission states
teach-skill security privacy         # Inspect privacy classification & retention
teach-skill security storage         # Verify filesystem & storage boundaries
teach-skill security network         # Verify zero-egress network isolation
teach-skill security integrity       # Verify cryptographic hash log
```

### Platform Subsystem
```bash
teach-skill platform info            # View platform OS and architecture
teach-skill platform capabilities    # Inspect capability matrix and degradation status
teach-skill platform permissions     # Audit OS-level permission states
teach-skill platform health          # Check platform adapter health
```

### Package & Migration Subsystem
```bash
teach-skill package validate         # Validate package integrity & checksums
teach-skill package info             # Inspect packaging manifest
teach-skill package health           # Verify packaging & migration subsystem
```

## 5. Security & Privacy Audit Verification

- **Real Platform Verified**: macOS 15.x on Apple Silicon.
- **Linux & Windows Adapters**: Validated via deterministic simulation and schema checks.
- **Zero Dangling References**: Data deletion cascades across skills, learning history, and caches.
