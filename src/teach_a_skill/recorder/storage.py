"""Session persistence, streaming JSONL event storage, and crash recovery."""

import hashlib
import json
from pathlib import Path
from typing import Any

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.recorder.events import Event, EventType
from teach_a_skill.recorder.screen import ScreenFrame
from teach_a_skill.recorder.session import SessionManifest, SessionState
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.recorder.storage")


class SessionStorage:
    """Manages on-disk layout, incremental streaming, and recovery for a recording session."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id

        # Root directory for this specific session
        self.session_dir = self.storage_manager.get_path("recordings", session_id)
        self.events_dir = self.session_dir / "events"
        self.frames_dir = self.session_dir / "frames"
        self.metadata_dir = self.session_dir / "metadata"

        self.events_file = self.events_dir / "events.jsonl"
        self.manifest_file = self.session_dir / "manifest.json"
        self.checksums_file = self.session_dir / "checksums.json"

        self._events_file_handle = None

    def initialize_session_layout(self, manifest: SessionManifest) -> None:
        """Create partitioned directory structure and persist initial manifest."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.save_manifest(manifest)
        self._events_file_handle = open(self.events_file, "a", encoding="utf-8")

    def append_event(self, event: Event) -> None:
        """Append event to events.jsonl with immediate flush for crash resilience."""
        if self._events_file_handle is None or self._events_file_handle.closed:
            self._events_file_handle = open(self.events_file, "a", encoding="utf-8")

        line = event.to_json() + "\n"
        self._events_file_handle.write(line)
        self._events_file_handle.flush()

    def save_frame(self, frame: ScreenFrame) -> Path:
        """Save frame PNG bytes to disk atomically."""
        frame_filename = f"{frame.frame_id}.{frame.image_format}"
        target_path = self.frames_dir / frame_filename
        self.storage_manager.write_atomic_bytes(target_path, frame.image_bytes)
        return target_path

    def save_metadata(self, name: str, data: dict[str, Any]) -> None:
        """Save ancillary metadata JSON."""
        target_path = self.metadata_dir / f"{name}.json"
        self.storage_manager.write_metadata(target_path, data)

    def save_manifest(self, manifest: SessionManifest) -> None:
        """Atomically persist session manifest."""
        self.storage_manager.write_metadata(self.manifest_file, manifest.to_dict())

    def close(self) -> None:
        """Close open file handles."""
        if self._events_file_handle and not self._events_file_handle.closed:
            self._events_file_handle.flush()
            self._events_file_handle.close()
            self._events_file_handle = None

    def finalize_session(
        self,
        manifest: SessionManifest,
        summary: dict[str, Any],
        frame_index: dict[str, Any],
    ) -> dict[str, str]:
        """Finalize recording, write summaries, and compute integrity checksums."""
        self.close()
        self.save_manifest(manifest)
        self.save_metadata("summary", summary)
        self.save_metadata("frame_index", frame_index)

        checksums = self.compute_checksums()
        self.storage_manager.write_metadata(self.checksums_file, checksums)
        return checksums

    def compute_checksums(self) -> dict[str, str]:
        """Compute SHA-256 hashes of critical session artifacts."""
        hashes: dict[str, str] = {}
        for target, name in [
            (self.manifest_file, "manifest.json"),
            (self.events_file, "events.jsonl"),
        ]:
            if target.exists():
                h = hashlib.sha256()
                with open(target, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                hashes[name] = h.hexdigest()
        return hashes

    def read_all_events(self) -> list[Event]:
        """Stream read all events from events.jsonl."""
        if not self.events_file.exists():
            return []

        events: list[Event] = []
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    events.append(Event.from_dict(data))
        return events

    @classmethod
    def recover_session(
        cls,
        storage_manager: StorageManager,
        session_id: str,
    ) -> SessionManifest:
        """Scan and repair an interrupted session after a crash or ungraceful shutdown.

        Recovers event count, verifies integrity, and marks status as ABORTED.
        """
        session_storage = cls(storage_manager, session_id)
        if not session_storage.manifest_file.exists():
            raise StorageError(f"Cannot recover session '{session_id}': manifest not found.")

        manifest_data = session_storage.storage_manager.read_metadata(session_storage.manifest_file)
        manifest = SessionManifest.from_dict(manifest_data)

        # If already COMPLETED or ABORTED, nothing to recover
        if manifest.status in (SessionState.COMPLETED, SessionState.ABORTED):
            return manifest

        # Read persisted events to compute actual state
        events = session_storage.read_all_events()
        has_stop_event = any(e.event_type == EventType.SESSION_STOPPED for e in events)

        manifest.event_count = len(events)
        manifest.status = SessionState.COMPLETED if has_stop_event else SessionState.ABORTED

        # Update event type distribution
        type_counts: dict[str, int] = {}
        for e in events:
            type_counts[str(e.event_type)] = type_counts.get(str(e.event_type), 0) + 1
        manifest.event_counts_by_type = type_counts

        session_storage.save_manifest(manifest)
        session_storage.finalize_session(
            manifest=manifest,
            summary={
                "recovery_note": "Recovered by SessionStorage crash handler",
                "recovered_events": len(events),
            },
            frame_index={},
        )

        logger.warning(
            f"Recovered interrupted session '{session_id}' with status {manifest.status} ({len(events)} events)."
        )
        return manifest
