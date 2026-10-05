"""Screen capture models, hybrid adaptive capture strategy, and frame indexing."""

import struct
import zlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class CaptureProfile(str, Enum):
    """Screen capture frequency and fidelity profile."""

    MINIMAL = "MINIMAL"  # Weak hardware: event-triggered only, no periodic checkpoints
    BALANCED = "BALANCED"  # Default: event-triggered + periodic checkpoint every 3.0s
    HIGH = "HIGH"  # High hardware: event-triggered + periodic checkpoint every 1.0s

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DisplayInfo:
    """Connected display monitor geometry and scaling."""

    display_id: int
    name: str
    width: int
    height: int
    scale_factor: float = 1.0
    is_primary: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenFrame:
    """Metadata and raw raster bytes for a captured screen checkpoint."""

    frame_id: str
    timestamp: str  # ISO 8601 UTC
    monotonic_timestamp: float
    display_id: int
    width: int
    height: int
    scale_factor: float
    trigger_reason: str  # "session_start", "mouse_click", "mouse_drag", "window_change", "periodic", "session_stop"
    triggering_event_id: Optional[str] = None
    previous_event_id: Optional[str] = None
    next_event_id: Optional[str] = None
    image_format: str = "png"
    image_bytes: bytes = field(default_factory=bytes, repr=False)

    def to_metadata_dict(self) -> dict[str, Any]:
        """Return frame descriptor excluding raw bytes."""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "monotonic_timestamp": self.monotonic_timestamp,
            "display_id": self.display_id,
            "width": self.width,
            "height": self.height,
            "scale_factor": self.scale_factor,
            "trigger_reason": self.trigger_reason,
            "triggering_event_id": self.triggering_event_id,
            "previous_event_id": self.previous_event_id,
            "next_event_id": self.next_event_id,
            "image_format": self.image_format,
            "byte_size": len(self.image_bytes),
        }


class FrameIndexer:
    """Maintains fast temporal associations between events and screenshots.

    Enables later AI systems to ask:
    - What was the screen state immediately before event X?
    - What was the resulting screen state after event X?
    """

    def __init__(self) -> None:
        # frame_id -> ScreenFrame metadata
        self._frames: dict[str, dict[str, Any]] = {}
        # Chronological list of (monotonic_ts, frame_id)
        self._timeline: list[tuple[float, str]] = []
        # event_id -> frame_id mapping
        self._event_to_frame: dict[str, str] = {}

    def register_frame(self, frame: ScreenFrame) -> None:
        meta = frame.to_metadata_dict()
        self._frames[frame.frame_id] = meta
        self._timeline.append((frame.monotonic_timestamp, frame.frame_id))

        if frame.triggering_event_id:
            self._event_to_frame[frame.triggering_event_id] = frame.frame_id

    def get_frame_for_event(self, event_id: str) -> Optional[dict[str, Any]]:
        frame_id = self._event_to_frame.get(event_id)
        return self._frames.get(frame_id) if frame_id else None

    def find_nearest_frame_before(self, monotonic_ts: float) -> Optional[dict[str, Any]]:
        """Find the most recent screen frame captured prior to a timestamp."""
        best_id: Optional[str] = None
        for ts, fid in self._timeline:
            if ts <= monotonic_ts:
                best_id = fid
            else:
                break
        return self._frames.get(best_id) if best_id else None

    def to_index_dict(self) -> dict[str, Any]:
        return {
            "total_frames": len(self._frames),
            "frames": list(self._frames.values()),
            "event_associations": self._event_to_frame,
        }


def encode_raw_rgb_to_png(width: int, height: int, rgb_bytes: bytes) -> bytes:
    """Pure standard-library PNG encoder using zlib and struct.

    Converts raw 24-bit RGB (or 32-bit RGBA) buffer into standard W3C PNG bytes
    with zero external dependencies.
    """
    is_rgba = len(rgb_bytes) == width * height * 4
    color_type = 6 if is_rgba else 2  # 6=RGBA, 2=RGB
    bytes_per_pixel = 4 if is_rgba else 3
    line_bytes = width * bytes_per_pixel

    # Prepend filter byte 0 (None) to each scanline
    raw_scanlines = bytearray()
    for y in range(height):
        raw_scanlines.append(0)  # filter type 0
        start = y * line_bytes
        raw_scanlines.extend(rgb_bytes[start : start + line_bytes])

    compressed_idat = zlib.compress(bytes(raw_scanlines), level=6)

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)

    png_signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)
    idat = make_chunk(b"IDAT", compressed_idat)
    iend = make_chunk(b"IEND", b"")

    return png_signature + ihdr + idat + iend


def create_solid_color_png(width: int, height: int, r: int = 40, g: int = 44, b: int = 52) -> bytes:
    """Generate a lightweight solid-color PNG for synthetic frames or fallback blanks."""
    raw = bytes([r, g, b]) * (width * height)
    return encode_raw_rgb_to_png(width, height, raw)
