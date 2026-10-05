"""Audio input device enumeration, capability discovery, and backend abstraction."""

import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger

logger = get_logger("teach_a_skill.teaching.audio.device")


@dataclass
class AudioDevice:
    """Represents a discovered audio input hardware device."""

    device_id: str
    name: str
    is_default: bool = False
    channels: int = 1
    default_sample_rate: int = 16000
    is_input: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AudioBackend:
    """Detects available system audio backends and enumerates input hardware."""

    def __init__(self) -> None:
        self.os_type = platform.system().lower()
        self.ffmpeg_path = shutil.which("ffmpeg")

    @property
    def is_available(self) -> bool:
        """Returns True if a valid audio recording mechanism is detected on the host."""
        if self.os_type == "darwin":
            # On macOS, avfoundation via ffmpeg or native audio recording tools
            return self.ffmpeg_path is not None or shutil.which("sox") is not None
        elif self.os_type == "linux":
            # On Linux, ALSA (arecord), PulseAudio (parecord), or ffmpeg
            return (
                shutil.which("arecord") is not None
                or shutil.which("parecord") is not None
                or self.ffmpeg_path is not None
            )
        elif self.os_type == "windows":
            return self.ffmpeg_path is not None
        return False

    def get_backend_name(self) -> str:
        """Return identifier of active audio backend."""
        if self.ffmpeg_path:
            return f"ffmpeg ({self.ffmpeg_path})"
        if shutil.which("sox"):
            return "sox"
        if shutil.which("arecord"):
            return "alsa (arecord)"
        if shutil.which("parecord"):
            return "pulseaudio (parecord)"
        return "synthetic-only"

    def list_input_devices(self) -> list[AudioDevice]:
        """Query and list available audio input devices."""
        devices: list[AudioDevice] = []

        if self.os_type == "darwin" and self.ffmpeg_path:
            # Query AVFoundation devices via ffmpeg
            try:
                cmd = [self.ffmpeg_path, "-f", "avfoundation", "-list_devices", "true", "-i", ""]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
                # ffmpeg writes device list to stderr
                output = res.stderr
                in_audio_section = False
                for line in output.splitlines():
                    if "AVFoundation audio devices:" in line:
                        in_audio_section = True
                        continue
                    if in_audio_section:
                        if "AVFoundation video devices:" in line or "error" in line.lower():
                            break
                        # Example: [AVFoundation input device @ 0x...] [0] Built-in Microphone
                        if "]" in line and "[" in line:
                            parts = line.split("]", 2)
                            if len(parts) >= 2:
                                dev_idx_str = parts[-2].strip("[").strip()
                                if dev_idx_str.isdigit():
                                    dev_name = parts[-1].strip()
                                    devices.append(
                                        AudioDevice(
                                            device_id=dev_idx_str,
                                            name=dev_name,
                                            is_default=(len(devices) == 0),
                                            channels=1,
                                            default_sample_rate=16000,
                                        )
                                    )
            except Exception as e:
                logger.debug(f"Could not parse macOS AVFoundation devices: {e}")

        # If no devices discovered or platform tool not present, provide clean default device
        if not devices:
            devices.append(
                AudioDevice(
                    device_id="default",
                    name="Default System Microphone",
                    is_default=True,
                    channels=1,
                    default_sample_rate=16000,
                )
            )

        return devices

    def get_default_input_device(self) -> Optional[AudioDevice]:
        """Return the default input audio device."""
        devices = self.list_input_devices()
        for d in devices:
            if d.is_default:
                return d
        return devices[0] if devices else None
