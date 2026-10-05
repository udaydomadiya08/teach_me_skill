"""Persistent storage manager for execution records, profiles, proposals, and learning audits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.learning.models import (
    CandidateSkillVersion,
    ExecutionRecord,
    ImprovementProposal,
    LearningAudit,
    LearningExperiment,
    SkillPerformanceProfile,
)
from teach_a_skill.storage.atomic import atomic_write


class LearningStore:
    """Manages persistent partitioned artifacts under the 'learning/' category."""

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.storage = storage_manager
        self.root_dir = self.storage.get_path("learning")
        self._init_subdirectories()

    def _init_subdirectories(self) -> None:
        for sub in ("records", "profiles", "patterns", "proposals", "candidates", "experiments", "audits"):
            (self.root_dir / sub).mkdir(parents=True, exist_ok=True)

    @classmethod
    def redact_sensitive(cls, data: Any) -> Any:
        """Recursively redact passwords, keys, and tokens from persisted dictionaries."""
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if any(s in k.lower() for s in ("password", "secret", "token", "auth", "credential", "private_key")):
                    clean[k] = "[REDACTED]"
                else:
                    clean[k] = cls.redact_sensitive(v)
            return clean
        elif isinstance(data, list):
            return [cls.redact_sensitive(item) for item in data]
        return data

    def save_execution_record(self, record: ExecutionRecord) -> Path:
        path = self.root_dir / "records" / f"{record.execution_id}.json"
        clean_data = self.redact_sensitive(record.to_dict())
        payload = json.dumps(clean_data, indent=2)
        atomic_write(path, payload)
        return path

    def load_execution_record(self, execution_id: str) -> Optional[dict[str, Any]]:
        path = self.root_dir / "records" / f"{execution_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_execution_records(self, skill_id: Optional[str] = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for p in (self.root_dir / "records").glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                    if skill_id is None or rec.get("skill_id") == skill_id:
                        records.append(rec)
            except Exception:
                pass
        return sorted(records, key=lambda r: r.get("timestamp", ""))

    def save_proposal(self, proposal: ImprovementProposal) -> Path:
        path = self.root_dir / "proposals" / f"{proposal.proposal_id}.json"
        payload = json.dumps(proposal.to_dict(), indent=2)
        atomic_write(path, payload)
        return path

    def list_proposals(self, skill_id: Optional[str] = None) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []
        for p in (self.root_dir / "proposals").glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    prop = json.load(f)
                    if skill_id is None or prop.get("skill_id") == skill_id:
                        proposals.append(prop)
            except Exception:
                pass
        return proposals

    def save_candidate(self, candidate: CandidateSkillVersion) -> Path:
        path = self.root_dir / "candidates" / f"{candidate.candidate_id}.json"
        payload = json.dumps(candidate.to_dict(), indent=2)
        atomic_write(path, payload)
        return path

    def list_candidates(self, skill_id: Optional[str] = None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for p in (self.root_dir / "candidates").glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cand = json.load(f)
                    if skill_id is None or cand.get("skill_id") == skill_id:
                        candidates.append(cand)
            except Exception:
                pass
        return candidates

    def save_audit(self, audit: LearningAudit) -> Path:
        path = self.root_dir / "audits" / f"{audit.audit_id}.json"
        payload = json.dumps(audit.to_dict(), indent=2)
        atomic_write(path, payload)
        return path

    def list_audits(self, skill_id: Optional[str] = None) -> list[dict[str, Any]]:
        audits: list[dict[str, Any]] = []
        for p in (self.root_dir / "audits").glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                    if skill_id is None or entry.get("skill_id") == skill_id:
                        audits.append(entry)
            except Exception:
                pass
        return sorted(audits, key=lambda a: a.get("timestamp", ""))
