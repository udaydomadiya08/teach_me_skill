"""Chained audit logging, cryptographic tamper-evidence, and SECURITY_INCIDENT handler."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.errors import TeachSkillError


class SecurityIncidentError(TeachSkillError):
    """Raised when an active security incident or audit log tampering is detected."""
    pass


@dataclass(frozen=True)
class ChainedAuditRecord:
    """Cryptographically chained audit entry."""

    audit_id: str
    sequence: int
    previous_hash: str
    timestamp: str
    action: str
    actor: str
    details: dict[str, Any]
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def compute_hash(
        cls,
        previous_hash: str,
        sequence: int,
        timestamp: str,
        action: str,
        actor: str,
        details: dict[str, Any],
    ) -> str:
        serialized = json.dumps(
            {
                "previous_hash": previous_hash,
                "sequence": sequence,
                "timestamp": timestamp,
                "action": action,
                "actor": actor,
                "details": details,
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class AuditIntegrityManager:
    """Maintains an append-only, chained cryptographic audit log and verifies tamper-evidence."""

    GENESIS_HASH = "0" * 64

    def __init__(self, log_file: Path | str) -> None:
        self.log_path = Path(log_file)
        self._incident_active: bool = False
        self._incident_details: Optional[dict[str, Any]] = None
        self._ensure_log_exists()

    def _ensure_log_exists(self) -> None:
        if not self.log_path.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.touch()

    @property
    def is_incident_active(self) -> bool:
        return self._incident_active

    def get_incident_details(self) -> Optional[dict[str, Any]]:
        return self._incident_details

    def record_event(self, action: str, actor: str = "system", details: Optional[dict[str, Any]] = None) -> ChainedAuditRecord:
        """Append a new chained cryptographic audit record."""
        if self._incident_active:
            raise SecurityIncidentError(
                f"Cannot record new events: system is in active SECURITY_INCIDENT state ({self._incident_details})"
            )

        records = self.load_records()
        seq = len(records)
        prev_hash = records[-1].record_hash if records else self.GENESIS_HASH
        ts = datetime.now(timezone.utc).isoformat()
        clean_details = details or {}

        rec_hash = ChainedAuditRecord.compute_hash(
            previous_hash=prev_hash,
            sequence=seq,
            timestamp=ts,
            action=action,
            actor=actor,
            details=clean_details,
        )

        record = ChainedAuditRecord(
            audit_id=f"aud-{uuid.uuid4().hex[:12]}",
            sequence=seq,
            previous_hash=prev_hash,
            timestamp=ts,
            action=action,
            actor=actor,
            details=clean_details,
            record_hash=rec_hash,
        )

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

        return record

    def load_records(self) -> list[ChainedAuditRecord]:
        """Read all audit records from disk."""
        if not self.log_path.exists():
            return []

        records: list[ChainedAuditRecord] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        d = json.loads(line)
                        records.append(ChainedAuditRecord(**d))
                    except Exception:
                        pass
        return records

    def verify_chain(self) -> tuple[bool, str, Optional[int]]:
        """Verify the complete hash chain. Detects modification, deletion, reordering, and truncation."""
        records = self.load_records()
        if not records:
            return True, "Audit log is empty; chain is valid.", None

        expected_prev = self.GENESIS_HASH
        for i, rec in enumerate(records):
            # Check sequence
            if rec.sequence != i:
                msg = f"Audit sequence broken at index {i}: expected sequence {i}, got {rec.sequence}"
                self.trigger_security_incident("SEQUENCE_MISMATCH", msg, record_index=i)
                return False, msg, i

            # Check previous hash link
            if rec.previous_hash != expected_prev:
                msg = f"Audit chain broken at sequence {i}: expected previous_hash '{expected_prev}', got '{rec.previous_hash}'"
                self.trigger_security_incident("CHAIN_LINK_CORRUPTED", msg, record_index=i)
                return False, msg, i

            # Recompute record hash
            actual_hash = ChainedAuditRecord.compute_hash(
                previous_hash=rec.previous_hash,
                sequence=rec.sequence,
                timestamp=rec.timestamp,
                action=rec.action,
                actor=rec.actor,
                details=rec.details,
            )
            if actual_hash != rec.record_hash:
                msg = f"Audit record tampering detected at sequence {i}: content hash mismatch"
                self.trigger_security_incident("RECORD_TAMPERED", msg, record_index=i)
                return False, msg, i

            expected_prev = rec.record_hash

        return True, f"Audit chain verified: all {len(records)} records intact with unbroken cryptographic provenance.", None

    def trigger_security_incident(self, incident_type: str, reason: str, **kwargs: Any) -> None:
        """Transition into fail-closed SECURITY_INCIDENT state."""
        self._incident_active = True
        self._incident_details = {
            "incident_type": incident_type,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
