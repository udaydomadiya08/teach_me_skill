"""Storage manager for Phase 6 multimodal artifacts."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.multimodal.models import (
    MultimodalManifest,
    MultimodalObservation,
    TemporalWindow,
)
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.multimodal.storage")


class MultimodalStorage:
    """Manages persistence and retrieval of derived multimodal intelligence artifacts."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id
        self.session_dir = storage_manager.get_path("recordings", session_id)
        self.multimodal_dir = self.session_dir / "multimodal"
        self.staging_dir = self.session_dir / ".multimodal_staging"

    def exists(self) -> bool:
        """Check if complete multimodal artifacts already exist for this session."""
        manifest_file = self.multimodal_dir / "manifest.json"
        obs_file = self.multimodal_dir / "observations.jsonl"
        return manifest_file.exists() and obs_file.exists()

    def read_manifest(self) -> Optional[MultimodalManifest]:
        """Read multimodal manifest."""
        manifest_file = self.multimodal_dir / "manifest.json"
        if not manifest_file.exists():
            return None
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MultimodalManifest.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read multimodal manifest for {self.session_id}: {e}")
            return None

    def read_observations(self) -> list[MultimodalObservation]:
        """Read all multimodal observations from JSONL."""
        obs_file = self.multimodal_dir / "observations.jsonl"
        if not obs_file.exists():
            return []
        observations: list[MultimodalObservation] = []
        with open(obs_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    observations.append(MultimodalObservation.from_dict(data))
                except Exception as e:
                    logger.warning(f"Corrupted observation line {line_no} in {obs_file}: {e}")
        return observations

    def read_windows(self) -> list[TemporalWindow]:
        """Read all temporal windows from JSONL."""
        win_file = self.multimodal_dir / "windows.jsonl"
        if not win_file.exists():
            return []
        windows: list[TemporalWindow] = []
        with open(win_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    windows.append(TemporalWindow.from_dict(json.loads(line)))
                except Exception:
                    pass
        return windows

    def write_multimodal_artifacts(
        self,
        windows: list[TemporalWindow],
        observations: list[MultimodalObservation],
        manifest: MultimodalManifest,
    ) -> None:
        """Persist multimodal artifacts atomically via staging directory."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        indexes_dir = self.staging_dir / "indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)

        obs_path = self.staging_dir / "observations.jsonl"
        win_path = self.staging_dir / "windows.jsonl"
        manifest_path = self.staging_dir / "manifest.json"
        index_path = indexes_dir / "multimodal_index.json"
        checksums_path = self.staging_dir / "checksums.json"

        # 1. Write observations.jsonl
        with open(obs_path, "w", encoding="utf-8") as f:
            for obs in observations:
                f.write(json.dumps(obs.to_dict()) + "\n")

        # 2. Write windows.jsonl
        with open(win_path, "w", encoding="utf-8") as f:
            for win in windows:
                f.write(json.dumps(win.to_dict()) + "\n")

        # 3. Build index
        index_data = {
            "by_id": {obs.observation_id: obs.to_dict() for obs in observations},
            "by_type": {},
            "by_evidence_type": {},
        }
        for obs in observations:
            obs_type = str(obs.observation_type)
            index_data["by_type"].setdefault(obs_type, []).append(obs.observation_id)
            for ref in obs.evidence_refs:
                index_data["by_evidence_type"].setdefault(ref.evidence_type, []).append(
                    obs.observation_id
                )

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

        # 4. Write manifest.json
        manifest.total_windows = len(windows)
        manifest.total_observations = len(observations)
        counts: dict[str, int] = {}
        for obs in observations:
            ot = str(obs.observation_type)
            counts[ot] = counts.get(ot, 0) + 1
        manifest.observation_counts_by_type = counts

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # 5. Compute SHA-256 checksums
        checksums = {}
        for p in [obs_path, win_path, manifest_path, index_path]:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            checksums[p.name] = h.hexdigest()

        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        # Atomic commit
        if self.multimodal_dir.exists():
            backup_dir = self.session_dir / ".multimodal_backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            self.multimodal_dir.rename(backup_dir)
            try:
                self.staging_dir.rename(self.multimodal_dir)
                shutil.rmtree(backup_dir, ignore_errors=True)
            except Exception as e:
                # Rollback
                if backup_dir.exists():
                    backup_dir.rename(self.multimodal_dir)
                raise e
        else:
            self.staging_dir.rename(self.multimodal_dir)

    def clean(self) -> None:
        """Remove derived multimodal artifacts (does not touch raw Phase 2-5 files)."""
        if self.multimodal_dir.exists():
            shutil.rmtree(self.multimodal_dir, ignore_errors=True)
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)
