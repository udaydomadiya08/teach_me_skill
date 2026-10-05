# Privacy Policy & Architecture

## 1. Core Commitment: Zero Leaks by Default

In a computer task teaching system, user demonstrations inevitably touch sensitive private information:
- Screen pixels and window frames containing confidential communications or bank details
- Keystroke streams containing passwords, PINs, or auth tokens
- Voice audio streams containing ambient conversations
- Active application titles, file paths, and local document names
- Compiled skills reflecting proprietary user workflows

Therefore, the core privacy architecture is built upon one non-negotiable rule:
**Nothing leaves the user's machine.**

---

## 2. Default Invariants

Phase 1 establishes and enforces the following default invariants:

| Policy Dimension | Default Value | Enforced By | Description |
| :--- | :--- | :--- | :--- |
| **Local Only** | `True` | `PrivacyGuard` | All execution, storage, and processing must occur locally. |
| **Network Access** | `False` (BLOCKED) | `PrivacyGuard` | No socket connections or HTTP requests permitted. |
| **Telemetry / Analytics** | `False` (DISABLED)| `PrivacyGuard` | Zero usage metrics or pingbacks transmitted. |
| **Cloud Inference** | `False` (DISABLED)| `PrivacyGuard` | All models run on local host hardware. |
| **Data Upload** | `False` (LOCKED) | `PrivacyGuard` | Hard-locked against remote data transmission. |
| **Local Persistence** | `True` | `StorageManager` | Stored exclusively in local sandboxed partitions. |
| **Screen Capture** | `False` (DISABLED)| `PrivacyGuard` | Disabled until explicit recording session in Phase 2. |
| **Microphone Capture**| `False` (DISABLED)| `PrivacyGuard` | Disabled until explicit voice session in Phase 3. |
| **Log Redaction** | `True` | `Logging` | Sensitive fields and credentials automatically masked. |

---

## 3. PrivacyGuard Runtime Enforcement

The system does not merely rely on documentation. `PrivacyGuard` (`teach_a_skill.privacy.guard`) provides runtime enforcement methods:

- `assert_network_allowed(target)`: Raises `PrivacyViolationError` if any component attempts external network access.
- `assert_telemetry_allowed()`: Raises `PrivacyViolationError` if any telemetry attempt occurs.
- `assert_cloud_inference_allowed()`: Raises `PrivacyViolationError` if remote model inference is invoked.
- `assert_screen_capture_allowed()`: Raises `PrivacyViolationError` if screen capture is initiated without an explicit active recording session.
- `assert_microphone_allowed()`: Raises `PrivacyViolationError` if audio capture is initiated without an explicit active voice session.

---

## 4. Privacy-Safe Structured Logging

Log files can inadvertently become privacy leak vectors if developers output raw event structures or user state. 

Teach A Skill includes a dedicated `PrivacySafeLogFormatter` in `teach_a_skill.core.logging`:
1. **Key Pattern Redaction**: Automatically scans dictionary keys and extra attributes against sensitive patterns (`password`, `secret`, `token`, `credential`, `keystroke`, `keypress`, `raw_audio`, `screen_buffer`, `screenshot`, `api_key`). Matching values are replaced with `[REDACTED_SENSITIVE]`.
2. **Binary Truncation**: Raw binary buffers (such as frame buffers or audio PCM data) are sanitized to metadata descriptions (e.g. `<binary_data: 65536 bytes>`).
3. **No Cloud Log Transmitters**: Logs are stored strictly on the local filesystem in the `logs/` directory.

---

## 5. Future Network & Cloud Extensions

If cloud inference or remote synchronization features are ever developed in future phases, the following rules apply:
1. They must be **strictly optional plugins** or adapters.
2. They must require **explicit user opt-in** in the configuration file.
3. The core engine will remain 100% operational when network access is completely disconnected.

---

## 6. Demonstration Recorder Privacy Controls (Phase 2)

Recording user desktop interactions presents acute privacy hazards (passwords, banking transactions, personal communications). Phase 2 implements multi-layered privacy guardrails directly in the capture pipeline:

### 1. Application-Level Exclusion
The `PrivacyFilter` automatically suppresses input capture and screen capture when excluded applications gain window focus. Built-in defaults include:
- Password Managers: `1Password`, `Bitwarden`, `KeePass`, `KeePassXC`, `Dashlane`, `LastPass`
- Private Communications: `Signal`, `WhatsApp`, `Telegram`
- Financial Tools: `Keychain Access`, banking and credential tools

### 2. Window Title Regular Expressions
Window titles matching sensitive patterns (e.g. `(?i)private\s*browsing`, `(?i)incognito`, `(?i)master\s*password`, `(?i)login`, `(?i)sign\s*in`, `(?i)2fa`, `(?i)otp`) automatically trigger input and screen capture masking.

### 3. Configurable Sensitive Input Policies
For keyboard input, the user can configure one of three discrete policies:
- **`RECORD`**: Physical key codes and characters are preserved (default for trusted local sessions).
- **`MASK`**: Keystrokes are recorded for timing and action presence, but the actual key name is replaced with `*` and physical codes are stripped.
- **`SUPPRESS`**: Keystrokes are completely dropped from the event timeline.

### 4. Global Pause & Recording Indicators
- Capture can be paused at any instant via hotkey or CLI, transitioning the state machine to `PAUSED`.
- While `PAUSED`, screen sampling, input hooking, and window context extraction are strictly disabled.
- The recorder status is continuously observable (`teach-skill record status`) and visibly logged (`● RECORDING`, `⏸ PAUSED`, `■ STOPPED`). The recorder NEVER operates covertly.

### 5. Explicit Data Inclusions & Exclusions
- **Captured in Phase 2**: Screen checkpoints, mouse coordinates/actions, physical keyboard events, active application/window metadata.
- **NOT Captured in Phase 2**: Webcam video, system clipboard content, browser history, filesystem files outside the recorded workspace.

---

## 7. Voice & Text Teaching Privacy Controls (Phase 3)

Microphone access introduces audio sensitivity (conversations, ambient sound, spoken credentials). Phase 3 implements strict privacy boundaries:

### 1. Explicit User Initiation Only
- Microphone capture requires explicit teaching initiation (`teach-skill teach start`).
- The system NEVER silently captures or polls audio in the background.

### 2. Visible Hardware Indicators
- Active audio capture is continuously signaled via CLI and logs:
  - `MIC: RECORDING` - Microphone actively streaming and chunking audio
  - `MIC: PAUSED` - Audio capture suspended, microphone hardware immediately released
  - `MIC: STOPPED` - Audio session completed or aborted
- The application never presents a fake recording indicator.

### 3. Immediate Pause & Release
- Calling `teach-skill teach pause` halts microphone acquisition instantaneously.
- No audio chunks are buffered or persisted during pause.
- Resuming requires explicit user action (`teach-skill teach resume`).

### 4. Zero Cloud Speech APIs (100% Offline Guarantee)
- Transcription is performed strictly by local models (`LocalWhisperSTTProvider` or `MockSTTProvider`).
- Outbound socket connections and remote speech APIs (Google Cloud Speech, Whisper API, AWS Transcribe) are prohibited and blocked by `PrivacyGuard`.
- All model weights and executables reside on local storage.

### 5. Transcript Logging Redaction
- In accordance with Section 51, complete spoken sentences and sensitive transcript texts are NEVER logged to standard application logs.
- Log statements record only metadata milestones (`audio backend initialized`, `audio chunk persisted`, `transcription completed`, `annotation created`).

### 6. Evidence Immutability & Separation
- Spoken audio (`audio/*.wav`), transcripts (`transcript.jsonl`), text notes (`text_notes.jsonl`), and annotations (`annotations.jsonl`) reside strictly in `teaching/` partitions.
- Phase 2 raw demonstration files (`events/events.jsonl`, `frames/`, `manifest.json`, `checksums.json`) are never rewritten or altered by teaching edits or transcript revisions.
