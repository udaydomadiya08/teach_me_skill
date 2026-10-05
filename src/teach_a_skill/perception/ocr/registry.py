"""OCR provider registry and hardware-adaptive resolver."""

from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.ocr.apple_vision import AppleVisionOCRProvider
from teach_a_skill.perception.ocr.base import OCRProvider
from teach_a_skill.perception.ocr.mock import MockOCRProvider
from teach_a_skill.perception.ocr.tesseract import TesseractOCRProvider

logger = get_logger("teach_a_skill.perception.ocr.registry")


def get_ocr_provider(
    name: Optional[str] = None,
    hardware_tier: Optional[str] = None,
) -> OCRProvider:
    """Resolve and return an available local OCR provider according to hardware tier and preferences."""
    if name == "mock" or name == "mock_ocr":
        return MockOCRProvider()

    if name == "apple_vision":
        prov = AppleVisionOCRProvider(accurate=(hardware_tier in ("HIGH", "ULTRA")))
        if prov.is_available():
            return prov
        raise RuntimeError("Apple Vision framework is requested but not available.")

    if name == "tesseract":
        prov = TesseractOCRProvider()
        if prov.is_available():
            return prov
        raise RuntimeError("Tesseract OCR is requested but not available.")

    # Auto-detection prioritizing native Apple Vision on macOS, then Tesseract, then Mock
    av_prov = AppleVisionOCRProvider(accurate=(hardware_tier in ("HIGH", "ULTRA")))
    if av_prov.is_available():
        logger.debug("Resolved local OCR provider: AppleVisionOCRProvider")
        return av_prov

    tess_prov = TesseractOCRProvider()
    if tess_prov.is_available():
        logger.debug("Resolved local OCR provider: TesseractOCRProvider")
        return tess_prov

    logger.warning("No native local OCR engine detected; defaulting to MockOCRProvider.")
    return MockOCRProvider()
