"""Teaching layer persistence, layout partitioning, and crash recovery."""

import hashlib
from typing import Any

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.store import TeachingAnnotationStore
from teach_a_skill.teaching.session import TeachingManifest, TeachingState
from teach_a_skill.teaching.transcript.store import TranscriptStore

logger = get_logger("teach_a_skill.teaching.storage")


class TeachingStorage:
    """Manages disk persistence and atomic updates for the teaching evidence layer.

    Strictly preserves raw Phase 2 demonstration files without mutation.
    """

    def __init__(self, storage_manager: StorageManager, recording_session_id: str) -> None:
        self.storage_manager = storage_manager
        self.recording_session_id = recording_session_id

        # Root demonstration directory
        self.session_dir = self.storage_manager.get_path("recordings", recording_session_id)
        # Separate isolated teaching partition
        self.teaching_dir = self.session_dir / "teaching"
        self.audio_dir = self.teaching_dir / "audio"

        self.manifest_file = self.teaching_dir / "manifest.json"
        self.checksums_file = self.teaching_dir / "checksums.json"
        self.transcript_file = self.teaching_dir / "transcript.jsonl"
        self.corrections_file = self.teaching_dir / "corrections.jsonl"
        self.annotations_file = self.teaching_dir / "annotations.jsonl"
        self.text_notes_file = self.teaching_dir / "text_notes.jsonl"

        self.transcript_store = TranscriptStore(self.transcript_file, self.corrections_file)
        self.annotation_store = TeachingAnnotationStore(self.annotations_file, self.text_notes_file)

    def initialize_teaching_layout(self, manifest: TeachingManifest) -> None:
        """Create teaching directory structure and persist initial manifest."""
        self.teaching_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.save_manifest(manifest)

    def save_manifest(self, manifest: Any) -> None:
        """Atomically persist teaching manifest."""
        data = manifest.to_dict() if hasattr(manifest, "to_dict") else dict(manifest)
        self.storage_manager.write_metadata(self.manifest_file, data)

    def compute_teaching_checksums(self) -> dict[str, str]:
        """Compute SHA-256 hashes for all teaching layer files."""
        hashes: dict[str, str] = {}
        for target, name in [
            (self.manifest_file, "manifest.json"),
            (self.transcript_file, "transcript.jsonl"),
            (self.corrections_file, "corrections.jsonl"),
            (self.annotations_file, "annotations.jsonl"),
            (self.text_notes_file, "text_notes.jsonl"),
        ]:
            if target.exists():
                h = hashlib.sha256()
                with open(target, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                hashes[name] = h.hexdigest()

        # Audio chunks hashes
        if self.audio_dir.exists():
            for wav_file in sorted(self.audio_dir.glob("*.wav")):
                h = hashlib.sha256()
                with open(wav_file, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                hashes[f"audio/{wav_file.name}"] = h.hexdigest()

        return hashes

    def finalize_teaching_session(self, manifest: TeachingManifest) -> dict[str, str]:
        """Finalize teaching session, flush stores, and write checksums."""
        self.transcript_store.close()
        self.annotation_store.close()
        self.save_manifest(manifest)
        checksums = self.compute_teaching_checksums()
        self.storage_manager.write_metadata(self.checksums_file, checksums)
        return checksums

    def close(self) -> None:
        self.transcript_store.close()
        self.annotation_store.close()

    def recover_session(self) -> dict[str, Any]:
        """Recover this teaching session: cleans up .tmp files and recalculates manifest."""
        cleaned = []
        if self.audio_dir.exists():
            for tmp_file in self.audio_dir.glob("*.tmp"):
                try:
                    tmp_file.unlink()
                    cleaned.append(str(tmp_file))
                except OSError:
                    pass

        for tmp_file in self.teaching_dir.glob("*.tmp"):
            try:
                tmp_file.unlink()
                cleaned.append(str(tmp_file))
            except OSError:
                pass

        manifest = self.recover_teaching_session(self.storage_manager, self.recording_session_id)
        return {"recovered": True, "manifest": manifest, "cleaned_tmp_files": cleaned}

    @classmethod
    def recover_teaching_session(
        cls,
        storage_manager: StorageManager,
        recording_session_id: str,
    ) -> TeachingManifest:
        """Recover an interrupted or crashed teaching session.

        Reconstructs chunk counts, transcripts, and annotations, marking status as ABORTED
        without altering the Phase 2 raw demonstration.
        """
        teaching_storage = cls(storage_manager, recording_session_id)
        if not teaching_storage.manifest_file.exists():
            raise StorageError(
                f"Cannot recover teaching session for recording '{recording_session_id}': manifest not found."
            )

        manifest_data = teaching_storage.storage_manager.read_metadata(
            teaching_storage.manifest_file
        )
        manifest = TeachingManifest.from_dict(manifest_data)

        if manifest.status in (TeachingState.COMPLETED, TeachingState.ABORTED):
            return manifest

        # Scan audio chunks
        audio_files = (
            list(teaching_storage.audio_dir.glob("*.wav"))
            if teaching_storage.audio_dir.exists()
            else []
        )
        manifest.audio_chunks = len(audio_files)

        # Scan transcript segments
        segments = teaching_storage.transcript_store.read_all_segments(only_active=False)
        manifest.transcript_segments = len(segments)

        # Scan annotations and notes
        annotations = teaching_storage.annotation_store.read_all_annotations(only_active=False)
        notes = teaching_storage.annotation_store.read_all_notes()
        manifest.annotations = len(annotations)
        manifest.text_notes = len(notes)

        # Mark status as ABORTED
        manifest.status = TeachingState.ABORTED
        teaching_storage.finalize_teaching_session(manifest)

        logger.warning(
            f"Recovered interrupted teaching session for recording '{recording_session_id}' "
            f"marked ABORTED ({manifest.audio_chunks} audio chunks, {manifest.transcript_segments} segments)."
        )
        return manifest
