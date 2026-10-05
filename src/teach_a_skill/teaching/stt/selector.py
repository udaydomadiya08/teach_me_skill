"""Hardware tier adaptive STT configuration and model selector."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.models.registry import ModelRegistry
from teach_a_skill.teaching.stt.local_whisper import LocalWhisperSTTProvider
from teach_a_skill.teaching.stt.mock_provider import MockSTTProvider
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider


@dataclass
class STTTierConfiguration:
    """Hardware tier configuration profile for local STT."""

    tier: str
    model_id: str
    threads: int
    chunk_duration_sec: float
    beam_size: int
    memory_limit_mb: int
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TIER_STT_PROFILES: dict[str, STTTierConfiguration] = {
    "BASELINE": STTTierConfiguration(
        tier="BASELINE",
        model_id="whisper-tiny-local",
        threads=2,
        chunk_duration_sec=2.0,
        beam_size=1,
        memory_limit_mb=150,
        description="Lightweight CPU-constrained speech transcription for baseline hardware.",
    ),
    "STANDARD": STTTierConfiguration(
        tier="STANDARD",
        model_id="whisper-base-local",
        threads=4,
        chunk_duration_sec=2.0,
        beam_size=2,
        memory_limit_mb=250,
        description="Balanced local speech transcription for modern multi-core systems.",
    ),
    "HIGH": STTTierConfiguration(
        tier="HIGH",
        model_id="whisper-small-local",
        threads=8,
        chunk_duration_sec=3.0,
        beam_size=5,
        memory_limit_mb=600,
        description="High-accuracy accelerated speech transcription for workstation hardware.",
    ),
}


def select_stt_configuration(hardware_tier: HardwareTier | str) -> STTTierConfiguration:
    """Resolve adaptive STT configuration based on hardware tier."""
    tier_str = str(hardware_tier).upper()
    return TIER_STT_PROFILES.get(tier_str, TIER_STT_PROFILES["BASELINE"])


def create_tier_stt_provider(
    hardware_tier: HardwareTier | str,
    fallback_to_mock: bool = True,
    model_registry: Optional[ModelRegistry] = None,
) -> tuple[ISpeechToTextProvider, STTTierConfiguration]:
    """Instantiate appropriate STT provider based on hardware tier.

    If the real local whisper model is available on disk, returns LocalWhisperSTTProvider.
    Otherwise returns MockSTTProvider (if fallback_to_mock=True) or unavailable LocalWhisperSTTProvider.
    """
    config = select_stt_configuration(hardware_tier)
    local_provider = LocalWhisperSTTProvider(model_id=config.model_id)

    if local_provider.is_available():
        return local_provider, config

    if fallback_to_mock:
        return MockSTTProvider(), config

    return local_provider, config
