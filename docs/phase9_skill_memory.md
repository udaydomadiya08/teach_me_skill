# Phase 9 — Skill Format, Memory & Versioning

> **Exact Phase 9 Boundary Principle:**
> Phase 9 provides persistent storage, deterministic semantic versioning, demonstration lineage, comparison diffs, duplicate detection, and structured search for skills.
> Phase 9 **DOES NOT** execute skills, replay interactions, synthesize OS commands, click, type, or autonomously operate the user's interface. Execution belongs strictly to Phase 10 and beyond.

---

## 1. Architectural Overview

Phase 9 turns compiled Phase 8 Skill IR artifacts into a durable, versioned, multi-demonstration skill memory system:

```text
Phase 8 Skill IR
       ↓
Canonical Skill Format (SkillRecord & SkillVersionRecord)
       ↓
Persistent Skill Memory (skills/ Partition, Staging, Lock)
       ↓
Skill Registry (Lifecycle, Semver, Immutability)
       ↓
Lineage & Relationships (Demonstration -> Skill -> Version)
       ↓
Comparison, Matching & Deduplication (Diffs, Variants, Conflicts)
       ↓
Reusable, Evolving Skill Knowledge
```

---

## 2. Canonical Skill Format

Defined in [`src/teach_a_skill/memory/models.py`](file:///Users/uday/Documents/uday_projects/teach_a_skill/src/teach_a_skill/memory/models.py):

### SkillRecord (Top-Level Identity)
- **`skill_id`**: Deterministic identity (e.g. `skill_902cf98d71c209f9`).
- **`canonical_name`**: Semantic title (e.g. `Skill: Custom Interaction`).
- **`description`**: Human-readable overview.
- **`status`**: `DRAFT`, `VALIDATED`, `PUBLISHED`, `SUPERSEDED`, `ARCHIVED`, `INVALID`, `CONFLICTED`.
- **`current_version`**: Active published version string (e.g. `1.0.0`).
- **`versions`**: Ordered list of published version strings.
- **`source_demonstrations`**: Source recording session IDs.
- **`tags`**, **`capabilities`**, **`dependencies`**: Semantic metadata.
- **`fingerprint`**: Canonical SHA-256 fingerprint.
- **`provenance`**: Lineage tracing back to Phase 7 understanding and Phase 1-6 raw traces.

### SkillVersionRecord (Immutable Version)
- **`skill_id`**: Associated skill identifier.
- **`version`**: Semantic version string (`MAJOR.MINOR.PATCH`).
- **`status`**: Lifecycle state.
- **`fingerprint`**: Content-addressed SHA-256 digest of normalized semantic fields.
- **`checksum`**: SHA-256 hash of `skill.json`.
- **`parent_version`**: Direct predecessor version string.
- **`supersedes`** / **`superseded_by`**: Explicit supersession chain.
- **`skill_ir`**: Full validated [`SkillIR`](file:///Users/uday/Documents/uday_projects/teach_a_skill/src/teach_a_skill/skill/models.py).

---

## 3. Semantic Versioning Rules

Automated version bump recommendation implemented in [`SkillComparator`](file:///Users/uday/Documents/uday_projects/teach_a_skill/src/teach_a_skill/memory/comparator.py):

1. **`PATCH`** (Non-semantic modifications):
   - Metadata, descriptions, documentation updates.
   - Internal representation adjustments preserving exact execution semantics.
2. **`MINOR`** (Backward-compatible semantic additions):
   - New optional parameters with defaults.
   - Additional supported targets or expanded grounding fallback strategies.
   - Additional verification checkpoints or non-destructive intermediate steps.
3. **`MAJOR`** (Breaking semantic changes):
   - Changed semantic goal or intent.
   - New required parameters or removal of existing parameters.
   - Parameter type or constraint alterations.
   - Incompatible step actions, step removals, or reordering of essential operations.
   - Changed required preconditions or expected postconditions.
4. **`CONFLICT`**:
   - Directly contradictory goals (e.g. `Save Document` vs `Delete Document`).
   - Mutually exclusive postconditions (e.g. `FILE_SAVED` vs `FILE_DELETED`).

---

## 4. Demonstration Lineage & Relationships

Multi-demonstration relationships are tracked via explicit records:
- **`DemonstrationLineageRecord`**: Links source recording sessions to specific skill versions with relationship type (`DERIVED_FROM`, `SUPPORTED_BY`, `REVISION_OF`).
- **`SkillRelationshipRecord`**: Tracks skill-to-skill links:
  - `SUPERSEDES` / `SUPERSEDED_BY`
  - `DUPLICATE_OF`: Detected near-identical semantic structures.
  - `VARIANT_OF`: Equivalent semantic goals achieved via alternate action pathways (e.g. keyboard shortcut vs UI button).
  - `CONFLICTS_WITH`: Contradictory goals under identical scope.
  - `GENERALIZES` / `SPECIALIZES`

---

## 5. Persistent Partition & Storage Architecture

```text
skills/
├── registry_index.json       # Fast global lookup and search index
├── .lock                     # Concurrency lock file
├── .skill_memory_staging/    # Atomic staging directory
└── <skill_id>/
    ├── manifest.json         # Top-level SkillRecord
    ├── versions/
    │   ├── 1.0.0/
    │   │   ├── skill.json             # Immutable SkillIR
    │   │   ├── checksum.json          # SHA-256 file hashes
    │   │   └── version_manifest.json  # SkillVersionRecord
    │   └── 1.0.1/
    ├── lineage/
    │   ├── demonstrations.jsonl       # Demonstration lineage records
    │   └── relationships.jsonl        # Inter-skill relationship links
    └── rollback/
        └── history.jsonl              # Active version rollback audit log
```

---

## 6. CLI Commands

```bash
# Display skill memory status, schema version, and policy invariants
teach-skill memory models

# Run Phase 9 health checks
teach-skill memory health

# List registered skills in persistent memory
teach-skill memory list

# Register a compiled skill or demonstration session into memory
teach-skill memory register <session_id_or_path>

# Show skill details, lineage, and rollback history
teach-skill memory show <skill_id>

# List all immutable versions of a skill
teach-skill memory versions <skill_id>

# Compare two versions of a skill and display diff + recommended bump
teach-skill memory compare <skill_id> <v1> <v2>

# Search skills by name, description, goal, tags, or dependencies
teach-skill memory search "<query>"

# Archive a skill or version without destroying history
teach-skill memory archive <skill_id> [version]

# Restore an archived skill or version to PUBLISHED
teach-skill memory restore <skill_id> [version]

# Validate storage integrity, checksums, and execution blocking
teach-skill memory validate

# Deterministically rebuild registry indexes from on-disk version manifests
teach-skill memory rebuild-index

# Run scaling benchmarks and stress tests
teach-skill memory benchmark
```
