"""Recovery storage partition manager for Phase 11.

Persists failure records, recovery attempts, recovery plans, checkpoints,
and verification results using atomic, corruption-resistant storage.
Enforces resume safety invariants: interrupted sessions must never resume
physical execution automatically or reuse stale coordinates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.execution.models import ExecutionCheckpoint
from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.recovery.models import (
    ExecutionOutcome,
    FailureRecord,
    RecoveryAttempt,
    RecoveryPlan,
    VerificationResult,
)
from teach_a_skill.storage.manager import StorageManager

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "credential", "auth"}


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively redact sensitive key-values from audit records."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_sensitive_data(v)
        return redacted
    elif isinstance(obj, list):
        return [redact_sensitive_data(item) for item in obj]
    return obj


class RecoveryStorage:
    """Sandboxed atomic storage manager for Phase 11 recovery data."""

    def __init__(self, storage_manager: Optional[IStorageManager] = None) -> None:
        if storage_manager is not None:
            self.sm = storage_manager
        else:
            from teach_a_skill.config.manager import ConfigManager
            cfg_mgr = ConfigManager()
            self.sm = StorageManager(Path(cfg_mgr.get_config().storage.data_directory))
        self.recovery_dir = self.sm.get_path("recovery")
        self.recovery_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        content = json.dumps(data, indent=2, sort_keys=True)
        self.sm.write_atomic_text(path, content)

    # --- Failure Records ---

    def save_failure_record(self, record: FailureRecord) -> Path:
        """Atomically persist a FailureRecord with sensitive data redacted."""
        redacted_data = redact_sensitive_data(record.to_dict())
        path = self.recovery_dir / f"failure_{record.failure_id}.json"
        self._write_json(path, redacted_data)
        return path

    def load_failure_record(self, failure_id: str) -> Optional[FailureRecord]:
        """Load and validate a FailureRecord, safely detecting corruption."""
        path = self.recovery_dir / f"failure_{failure_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(self.sm.read_text(path))
            return FailureRecord.from_dict(data)
        except Exception as e:
            logger.error("Corrupted failure record detected at %s: %s", path, e)
            return None

    # --- Recovery Plans ---

    def save_recovery_plan(self, plan: RecoveryPlan) -> Path:
        """Atomically persist a RecoveryPlan."""
        path = self.recovery_dir / f"plan_{plan.plan_id}.json"
        self._write_json(path, plan.to_dict())
        return path

    def load_recovery_plan(self, plan_id: str) -> Optional[RecoveryPlan]:
        """Load and validate a RecoveryPlan, safely detecting corruption."""
        path = self.recovery_dir / f"plan_{plan_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(self.sm.read_text(path))
            return RecoveryPlan.from_dict(data)
        except Exception as e:
            logger.error("Corrupted recovery plan detected at %s: %s", path, e)
            return None

    # --- Recovery Attempts ---

    def save_recovery_attempt(self, attempt: RecoveryAttempt) -> Path:
        """Atomically persist a RecoveryAttempt audit log."""
        redacted_data = redact_sensitive_data(attempt.to_dict())
        path = self.recovery_dir / f"attempt_{attempt.attempt_id}.json"
        self._write_json(path, redacted_data)
        return path

    def load_recovery_attempt(self, attempt_id: str) -> Optional[RecoveryAttempt]:
        """Load and validate a RecoveryAttempt."""
        path = self.recovery_dir / f"attempt_{attempt_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(self.sm.read_text(path))
            return RecoveryAttempt.from_dict(data)
        except Exception as e:
            logger.error("Corrupted recovery attempt detected at %s: %s", path, e)
            return None

    # --- Checkpoints ---

    def save_checkpoint(self, checkpoint: ExecutionCheckpoint) -> Path:
        """Atomically persist an execution checkpoint."""
        path = self.recovery_dir / f"checkpoint_{checkpoint.checkpoint_id}.json"
        self._write_json(path, checkpoint.to_dict())
        return path

    def load_checkpoint(self, checkpoint_id: str) -> Optional[ExecutionCheckpoint]:
        """Load and validate an ExecutionCheckpoint."""
        path = self.recovery_dir / f"checkpoint_{checkpoint_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(self.sm.read_text(path))
            return ExecutionCheckpoint.from_dict(data)
        except Exception as e:
            logger.error("Corrupted checkpoint detected at %s: %s", path, e)
            return None

    # --- Session State & Crash Recovery ---

    def save_session_state(
        self,
        execution_id: str,
        status: str,
        completed_steps: list[str],
        current_step_id: Optional[str] = None,
        last_checkpoint_id: Optional[str] = None,
        interrupted: bool = False,
        resume_authorized: bool = False,
    ) -> Path:
        """Atomically persist execution session state for crash recovery."""
        path = self.recovery_dir / f"session_{execution_id}.json"
        payload = {
            "execution_id": execution_id,
            "status": status,
            "completed_steps": completed_steps,
            "current_step_id": current_step_id,
            "last_checkpoint_id": last_checkpoint_id,
            "interrupted": interrupted,
            "resume_authorized": resume_authorized,
        }
        self._write_json(path, payload)
        return path

    def load_session_state(self, execution_id: str) -> Optional[dict[str, Any]]:
        """Load session state with corruption check."""
        path = self.recovery_dir / f"session_{execution_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(self.sm.read_text(path))
        except Exception as e:
            logger.error("Corrupted session state detected at %s: %s", path, e)
            return None

    def recover_interrupted_session(self, execution_id: str) -> dict[str, Any]:
        """Recover an interrupted session and verify resume safety constraints.

        Rule: Process crash must NOT automatically resume physical execution.
        Must require explicit resume authorization.
        """
        session = self.load_session_state(execution_id)
        if not session:
            return {
                "can_resume": False,
                "reason": "Session not found or corrupted",
                "session": None,
            }

        required_keys = {"execution_id", "status", "completed_steps", "interrupted"}
        if not required_keys.issubset(session.keys()):
            return {
                "can_resume": False,
                "reason": "Session state metadata invalid or corrupted",
                "session": None,
            }

        if session.get("status") not in ("COMPLETED", "FAILED") and not session.get("interrupted"):
            session["interrupted"] = True
            session["status"] = "INTERRUPTED"
            self.save_session_state(
                execution_id=execution_id,
                status="INTERRUPTED",
                completed_steps=session.get("completed_steps", []),
                current_step_id=session.get("current_step_id"),
                last_checkpoint_id=session.get("last_checkpoint_id"),
                interrupted=True,
                resume_authorized=False,
            )

        resume_authorized = session.get("resume_authorized", False)
        if not resume_authorized:
            return {
                "can_resume": False,
                "reason": "Explicit resume authorization required. Automatic resumption is prohibited.",
                "session": session,
            }

        return {
            "can_resume": True,
            "reason": "Resume authorized; requires fresh environment observation and checkpoint revalidation",
            "session": session,
        }

    # --- Query & Inspection ---

    def list_failures(self, execution_id: Optional[str] = None) -> list[FailureRecord]:
        """List persisted failure records, optionally filtered by execution_id."""
        records: list[FailureRecord] = []
        for path in self.recovery_dir.glob("failure_*.json"):
            try:
                data = json.loads(self.sm.read_text(path))
                rec = FailureRecord.from_dict(data)
                if execution_id is None or rec.execution_id == execution_id:
                    records.append(rec)
            except Exception:
                continue
        return sorted(records, key=lambda r: r.timestamp)

    def list_recovery_attempts(self, failure_id: Optional[str] = None) -> list[RecoveryAttempt]:
        """List persisted recovery attempts, optionally filtered by failure_id."""
        attempts: list[RecoveryAttempt] = []
        for path in self.recovery_dir.glob("attempt_*.json"):
            try:
                data = json.loads(self.sm.read_text(path))
                att = RecoveryAttempt.from_dict(data)
                if failure_id is None or att.failure_id == failure_id:
                    attempts.append(att)
            except Exception:
                continue
        return sorted(attempts, key=lambda a: a.timestamp)
