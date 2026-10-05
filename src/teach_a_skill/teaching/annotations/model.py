"""Text annotations and note models for teaching demonstrations."""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AnnotationType(str, Enum):
    """Semantic category for human-provided teaching annotations."""

    INSTRUCTION = "instruction"
    EXPLANATION = "explanation"
    WARNING = "warning"
    CONTEXT = "context"
    CORRECTION = "correction"
    NOTE = "note"
    GOAL_HINT = "goal_hint"  # User-provided hint, NOT AI inferred

    def __str__(self) -> str:
        return self.value


@dataclass
class TeachingAnnotation:
    """Strongly structured, timestamped text annotation attached to timeline positions."""

    annotation_id: str
    teaching_session_id: str
    created_monotonic_ns: int
    start_monotonic_ns: int
    end_monotonic_ns: int
    text: str
    type: AnnotationType
    author: str = "user"
    revision: int = 1
    is_active: bool = True
    references: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = str(self.type)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeachingAnnotation":
        atype = data.get("type", "note")
        try:
            enum_type = AnnotationType(atype)
        except ValueError:
            enum_type = AnnotationType.NOTE

        return cls(
            annotation_id=data["annotation_id"],
            teaching_session_id=data["teaching_session_id"],
            created_monotonic_ns=int(data["created_monotonic_ns"]),
            start_monotonic_ns=int(data["start_monotonic_ns"]),
            end_monotonic_ns=int(data["end_monotonic_ns"]),
            text=data["text"],
            type=enum_type,
            author=data.get("author", "user"),
            revision=int(data.get("revision", 1)),
            is_active=data.get("is_active", True),
            references=data.get("references", {}),
            schema_version=data.get("schema_version", "1.0"),
        )


@dataclass
class TextNote:
    """Lightweight unstructured text note recorded during teaching."""

    note_id: str
    teaching_session_id: str
    timestamp_monotonic_ns: int
    wall_time: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextNote":
        return cls(
            note_id=data["note_id"],
            teaching_session_id=data["teaching_session_id"],
            timestamp_monotonic_ns=int(data["timestamp_monotonic_ns"]),
            wall_time=data["wall_time"],
            text=data["text"],
        )
