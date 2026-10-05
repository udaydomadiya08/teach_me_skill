"""Execution storage: persistent session artifacts and audit trails.

Stores execution sessions, plans, manifests, and checkpoints using
the project's standard atomic storage patterns.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.execution.models import (
    ExecutionManifest,
    ExecutionSession,
)
from teach_a_skill.interfaces.storage import IStorageManager

logger = logging.getLogger(__name__)


class ExecutionStorage:
    """Persistent storage for execution sessions and artifacts."""

    def __init__(
        self,
        storage_manager: IStorageManager,
        session_id: str = "",
    ) -> None:
        self.storage_manager = storage_manager
        self._session_id = session_id
        self._root = storage_manager.get_path("execution")
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root

    def get_session_dir(self, session_id: str) -> Path:
        """Get the directory for a specific execution session."""
        session_dir = self._root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def save_session(self, session: ExecutionSession) -> Path:
        """Atomically save an execution session to disk."""
        session_dir = self.get_session_dir(session.session_id)
        session_path = session_dir / "session.json"
        content = json.dumps(session.to_dict(), indent=2, sort_keys=True)
        self.storage_manager.write_atomic_text(session_path, content)
        logger.info("Saved execution session: %s", session.session_id)
        return session_path

    def load_session(self, session_id: str) -> Optional[ExecutionSession]:
        """Load an execution session from disk."""
        session_dir = self.get_session_dir(session_id)
        session_path = session_dir / "session.json"
        if not session_path.exists():
            return None
        try:
            content = self.storage_manager.read_text(session_path)
            data = json.loads(content)
            return ExecutionSession.from_dict(data)
        except Exception as e:
            logger.error("Failed to load session %s: %s", session_id, e)
            return None

    def save_manifest(self, manifest: ExecutionManifest) -> Path:
        """Save an execution manifest."""
        session_dir = self.get_session_dir(manifest.session_id)
        manifest_path = session_dir / "manifest.json"
        content = json.dumps(manifest.to_dict(), indent=2, sort_keys=True)
        self.storage_manager.write_atomic_text(manifest_path, content)
        return manifest_path

    def load_manifest(self, session_id: str) -> Optional[ExecutionManifest]:
        """Load an execution manifest."""
        session_dir = self.get_session_dir(session_id)
        manifest_path = session_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            content = self.storage_manager.read_text(manifest_path)
            data = json.loads(content)
            return ExecutionManifest.from_dict(data)
        except Exception as e:
            logger.error("Failed to load manifest %s: %s", session_id, e)
            return None

    def list_sessions(self) -> list[str]:
        """List all stored execution session IDs."""
        if not self._root.exists():
            return []
        return sorted(
            d.name
            for d in self._root.iterdir()
            if d.is_dir() and (d / "session.json").exists()
        )

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists on disk."""
        return (self._root / session_id / "session.json").exists()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its artifacts."""
        session_dir = self._root / session_id
        if not session_dir.exists():
            return False
        import shutil

        shutil.rmtree(session_dir)
        return True
