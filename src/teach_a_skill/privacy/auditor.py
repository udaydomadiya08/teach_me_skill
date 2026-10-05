"""PrivacyAuditor, data minimization inspector, user data exporter, and deletion verifier."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.errors import TeachSkillError
from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.security.secrets import SecretDetector


class PrivacyClassification(str, Enum):
    """Canonical data classification levels."""

    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PrivacyAuditItem:
    """Audit entry evaluating a stored artifact's privacy status."""

    artifact_path: str
    category: str
    classification: PrivacyClassification
    contains_secrets: bool
    is_redacted: bool
    sensitive_keys_found: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["classification"] = self.classification.value
        return data


class PrivacyAuditor:
    """Inspects stored artifacts for data minimization, privacy classifications, and redaction compliance."""

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.storage = storage_manager

    def audit_storage(self) -> list[PrivacyAuditItem]:
        """Perform recursive privacy audit across all storage partitions."""
        items: list[PrivacyAuditItem] = []
        root = self.storage.base_dir

        for p in root.rglob("*.json"):
            if not p.is_file() or p.name.startswith("."):
                continue

            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                    data = json.loads(content)

                # Classify
                rel_parts = p.relative_to(root).parts
                cat = rel_parts[0] if rel_parts else "misc"

                # Check secrets
                matches = SecretDetector.scan_text(content)
                contains_unredacted = any("[REDACTED" not in m.redacted_preview for m in matches)
                is_redacted = "[REDACTED" in content or not matches

                sens_keys: list[str] = []
                if isinstance(data, dict):
                    for k in data.keys():
                        if any(s in k.lower() for s in SecretDetector.SENSITIVE_KEY_NAMES):
                            sens_keys.append(k)

                classification = PrivacyClassification.PUBLIC
                if sens_keys or matches:
                    classification = PrivacyClassification.SENSITIVE
                elif cat in ("recordings", "perception"):
                    classification = PrivacyClassification.PERSONAL

                items.append(
                    PrivacyAuditItem(
                        artifact_path=str(p.relative_to(root)),
                        category=cat,
                        classification=classification,
                        contains_secrets=len(matches) > 0,
                        is_redacted=is_redacted,
                        sensitive_keys_found=sens_keys,
                    )
                )
            except Exception:
                pass

        return items


class UserDataExporter:
    """Exports user-owned skills, timelines, and learning records preserving provenance and checksums."""

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.storage = storage_manager

    def export_user_data(self, target_export_dir: Path | str) -> dict[str, Any]:
        """Produce portable user-data bundle with integrity manifest."""
        out_dir = Path(target_export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        exported_files: list[dict[str, Any]] = []
        root = self.storage.base_dir

        for sub in ("skills", "memory", "learning"):
            sub_path = self.storage.get_path(sub)
            if not sub_path.exists():
                continue
            dest_sub = out_dir / sub
            dest_sub.mkdir(parents=True, exist_ok=True)

            for f in sub_path.rglob("*.json"):
                if f.is_file():
                    content = f.read_bytes()
                    h = hashlib.sha256(content).hexdigest()
                    dest_file = dest_sub / f.name
                    dest_file.write_bytes(content)
                    exported_files.append({
                        "category": sub,
                        "file_name": f.name,
                        "sha256": h,
                        "size_bytes": len(content),
                    })

        manifest = {
            "export_version": "1.0.0",
            "source_app": "Teach A Skill",
            "file_count": len(exported_files),
            "files": exported_files,
        }
        (out_dir / "export_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


class UserDataDeleter:
    """Executes controlled user data deletion and verifies absence of dangling references."""

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.storage = storage_manager

    def delete_skill_data(self, skill_id: str) -> dict[str, Any]:
        """Delete all artifacts associated with skill_id across memory and learning partitions."""
        deleted: list[str] = []
        root = self.storage.base_dir

        for f in root.rglob("*.json"):
            if not f.is_file():
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if data.get("skill_id") == skill_id:
                        f.unlink()
                        deleted.append(str(f.relative_to(root)))
            except Exception:
                pass

        # Post-deletion integrity check: ensure zero dangling references remain
        dangling_refs: list[str] = []
        for f in root.rglob("*.json"):
            if not f.is_file():
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    content = fp.read()
                    if skill_id in content:
                        dangling_refs.append(str(f.relative_to(root)))
            except Exception:
                pass

        return {
            "skill_id": skill_id,
            "deleted_count": len(deleted),
            "deleted_files": deleted,
            "dangling_references": dangling_refs,
            "integrity_verified": len(dangling_refs) == 0,
        }
