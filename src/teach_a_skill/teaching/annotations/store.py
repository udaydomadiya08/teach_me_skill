"""Teaching annotations and text notes persistence store."""

import json
import threading
from pathlib import Path
from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.annotations.model import TeachingAnnotation, TextNote

logger = get_logger("teach_a_skill.teaching.annotations.store")


class TeachingAnnotationStore:
    """Manages streaming JSONL append and querying for annotations and text notes."""

    def __init__(self, annotations_file: Path, text_notes_file: Optional[Path] = None) -> None:
        self.annotations_file = annotations_file
        self.text_notes_file = text_notes_file or annotations_file.parent / "text_notes.jsonl"
        self._lock = threading.Lock()

        self.annotations_file.parent.mkdir(parents=True, exist_ok=True)
        self._annotations_handle = None
        self._notes_handle = None

    def append_annotation(self, annotation: TeachingAnnotation) -> None:
        """Append a teaching annotation with immediate flush."""
        with self._lock:
            if self._annotations_handle is None or self._annotations_handle.closed:
                self._annotations_handle = open(self.annotations_file, "a", encoding="utf-8")
            self._annotations_handle.write(annotation.to_json() + "\n")
            self._annotations_handle.flush()

    def append_note(self, note: TextNote) -> None:
        """Append a text note with immediate flush."""
        with self._lock:
            if self._notes_handle is None or self._notes_handle.closed:
                self._notes_handle = open(self.text_notes_file, "a", encoding="utf-8")
            self._notes_handle.write(note.to_json() + "\n")
            self._notes_handle.flush()

    def read_all_annotations(self, only_active: bool = True) -> list[TeachingAnnotation]:
        """Read all annotations from disk."""
        if not self.annotations_file.exists():
            return []

        annotations: list[TeachingAnnotation] = []
        with open(self.annotations_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    ann = TeachingAnnotation.from_dict(data)
                    if not only_active or ann.is_active:
                        annotations.append(ann)
        return annotations

    def read_all_notes(self) -> list[TextNote]:
        """Read all text notes from disk."""
        if not self.text_notes_file.exists():
            return []

        notes: list[TextNote] = []
        with open(self.text_notes_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    notes.append(TextNote.from_dict(data))
        return notes

    def rewrite_annotations(self, annotations: list[TeachingAnnotation]) -> None:
        """Atomically rewrite annotations file (used for updates and revisions)."""
        with self._lock:
            self.close()
            tmp_file = self.annotations_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                for ann in annotations:
                    f.write(ann.to_json() + "\n")
                f.flush()
            tmp_file.replace(self.annotations_file)

    def close(self) -> None:
        """Close open file handles."""
        if self._annotations_handle and not self._annotations_handle.closed:
            self._annotations_handle.flush()
            self._annotations_handle.close()
            self._annotations_handle = None
        if self._notes_handle and not self._notes_handle.closed:
            self._notes_handle.flush()
            self._notes_handle.close()
            self._notes_handle = None
