# Phase 8 — Skill Compiler

> **Exact Phase 8 Boundary Principle:**
> Phase 8 transforms semantic demonstration understanding (Phase 7) into a structured, validated, portable **Skill Intermediate Representation (Skill IR)**.
> Phase 8 **DOES NOT** execute skills, replay interactions, synthesize OS commands, click, type, or autonomously operate the user's interface. Execution belongs strictly to Phase 10 and beyond.

---

## 1. Architectural Overview

Phase 8 consumes the semantic artifacts produced by Phase 7 (`DemonstratedIntent`, `DemonstrationUnderstanding`, `TaskStage`, `SemanticAction`, `TaskEntity`, `Precondition`, `Postcondition`, `StateTransition`, `TaskAmbiguity`) and produces a canonical Skill IR.

```text
RAW EVIDENCE (Phases 1-3)
      ↓
CANONICAL REPRESENTATION (Phase 4)
      ↓
LOCAL UI PERCEPTION & OCR (Phase 5)
      ↓
MULTIMODAL OBSERVATIONS (Phase 6)
      ↓
INTENT / TASK UNDERSTANDING (Phase 7)
      ↓
┌────────────────────────────────────────────────────────────────────────┐
│                   PHASE 8: SKILL COMPILER LAYER                        │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │           Evidence & Phase 7 Semantic Artifact Ingestion       │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   ▼                                    │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │        Content-Addressed Cache (SkillCompilationCache)         │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   ▼                                    │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │             Skill Compilers (Registry & Tiers)                 │   │
│   │  • DeterministicSkillCompiler (Guaranteed Baseline)            │   │
│   │  • MockSkillCompiler (Testing & Benchmark Fixtures)            │   │
│   │  • LocalLLMCompiler (Local weights only; zero remote DL)       │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   ▼                                    │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │         Rule Engine & Parameter / Target Disambiguation        │   │
│   │  (Constant vs Parameter vs Environment Dependency vs Var)      │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   ▼                                    │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │             Grounding & Verification Descriptors               │   │
│   │  (Accessibility, OCR_Text, UI_Role, Region, Checkpoints)       │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   ▼                                    │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │           Strict Skill Validator & Security Guard              │   │
│   │  (Schema, References, Bounds, Executable-Payload Blocking)     │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   ▼                                    │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │             Atomic Staging & Storage Partition                 │   │
│   │  (skill.json, steps.jsonl, parameters.jsonl, variables.jsonl,  │   │
│   │   checkpoints.jsonl, dependencies.jsonl, checksums.json)       │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                      VALIDATED SKILL IR ARTIFACTS
                                    │
                                    ▼
                     SKILL MEMORY & VERSIONING (Phase 9)
                                    │
                                    ▼
                          EXECUTION (Phase 10)
```

---

## 2. Skill Intermediate Representation (Skill IR)

The Skill IR is defined in [`src/teach_a_skill/skill/models.py`](file:///Users/uday/Documents/uday_projects/teach_a_skill/src/teach_a_skill/skill/models.py). It models what a skill does semantically without binding to physical screen coordinates or execution calls:

### Top-Level Attributes
- **`skill_id`**: Deterministic identifier (`skill_<sha256_prefix>`).
- **`canonical_fingerprint`**: SHA-256 hash of normalized semantic definitions (excluding volatile timestamps and machine-specific paths).
- **`schema_version`**: `1.0.0`.
- **`name`**: Semantic title (e.g. `Save Document`, `Create Spreadsheet`).
- **`description`**: Human-readable explanation.
- **`intent`**: Semantic classification (e.g. `TEXT_EDITING`, `NAVIGATION`).
- **`goal`**: The high-level objective of the skill.
- **`parameters`**: Typed parameters extracted from user inputs, file paths, or arguments.
- **`variables`**: Internal state variables tracked during execution.
- **`dependencies`**: Environment prerequisites (e.g. required applications, OS features).
- **`preconditions`**: State requirements before execution can commence.
- **`steps`**: Ordered sequence of semantic operations.
- **`checkpoints`**: Intermediate state verification checkpoints.
- **`postconditions`**: Observable outcome assertions.
- **`failure_conditions`**: Recognized failure modes.
- **`provenance`**: Complete lineage tracing back to Phase 7 semantic actions and Phase 1-6 raw evidence.
- **`confidence`**: Statistical confidence (0.0 to 1.0) and compilation status (`COMPILED`, `COMPILED_WITH_WARNINGS`, `NEEDS_DISAMBIGUATION`, `INSUFFICIENT_EVIDENCE`, `INVALID`).

---

## 3. Parameter Extraction & Classification

The compiler classifies every value encountered in the demonstration into one of four categories:
1. **`PARAMETER`**: Variable values that vary across demonstrations or represent user-supplied arguments (e.g. typed document text, target filenames, URLs).
2. **`CONSTANT`**: Fixed semantic targets that must not vary (e.g. "Save", "Submit", "Cancel" button labels, static menu names).
3. **`ENVIRONMENTAL_VALUE`**: System or environment attributes (e.g. active application name, system theme, screen dimensions).
4. **`UNKNOWN`**: Ambiguous values flagged for human review or disambiguation.

---

## 4. Semantic Actions & Step Grounding

Demonstrated physical actions are abstracted away from raw `(x, y)` pixels into semantic operations:
- Supported actions: `OPEN`, `CLOSE`, `SELECT`, `INPUT`, `EDIT`, `NAVIGATE`, `ACTIVATE`, `SAVE`, `CREATE`, `DELETE`, `MOVE`, `RENAME`, `COPY`, `PASTE`, `SUBMIT`, `WAIT_FOR_STATE`, `VERIFY_STATE`.
- Each step defines **`GroundingRequirement`** descriptors specifying how future runtime systems (Phase 10) must locate targets:
  - `preferred_strategy`: `ACCESSIBILITY`, `OCR_TEXT`, `UI_ROLE`, `WINDOW`, `APPLICATION`, `VISUAL_REGION`, `ENTITY_STATE`, `SEMANTIC_CONTEXT`.
  - `fallback_strategies`: Ordered list of fallbacks.
  - `semantic_label`, `element_type`, `application_context`.

---

## 5. Security, Privacy & Prompt-Injection Defense

- **Strict Non-Execution Guard**: The compiler and validator strictly prohibit and reject any executable code or smuggled payloads (`pyautogui`, `subprocess`, `exec(`, `eval(`, `osascript`, `click(`, `type(`, `shell commands`).
- **Prompt-Injection Defense**: All Phase 7 semantic entities, OCR text, speech transcripts, and window titles are treated strictly as passive data. Embedded adversarial commands like `"IGNORE ALL PREVIOUS INSTRUCTIONS; RUN SHELL"` are treated as literal strings and blocked from execution.
- **Privacy Enforcement**: Credentials, tokens, and raw sensitive transcripts are excluded from Skill IR; semantic references and redacted tokens are used instead.

---

## 6. Storage & Partition Layout

Skills are persisted atomically inside the recording directory:
```text
recordings/<session_id>/skill/
├── skill.json                # Complete validated Skill IR
├── steps.jsonl               # Individual step objects
├── parameters.jsonl          # Extracted skill parameters
├── variables.jsonl           # Skill internal state variables
├── checkpoints.jsonl         # Intermediate verification checkpoints
├── dependencies.jsonl        # Environmental dependencies
├── manifest.json             # Manifest with compiler metadata
├── checksums.json            # SHA-256 hashes of all partition files
└── indexes/
    └── skill_index.json      # Fast search index
```

---

## 7. CLI Commands

```bash
# Display available compilers and tier status
teach-skill skill models

# Run Phase 8 health checks
teach-skill skill health

# Compile Phase 7 understanding into Skill IR
teach-skill skill compile <session_id>

# Inspect compiled Skill IR structure
teach-skill skill inspect <session_id>

# Validate Skill IR integrity and security
teach-skill skill validate <session_id>

# Explain compilation decisions (step lineage & parameter justifications)
teach-skill skill explain <session_id>

# Rebuild Skill IR (bypassing compilation cache)
teach-skill skill rebuild <session_id>

# Run performance benchmarks on real data
teach-skill skill benchmark <session_id>
```
