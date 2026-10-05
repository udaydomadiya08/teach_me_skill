"""Local Optical Character Recognition provider subsystem."""

from teach_a_skill.perception.ocr.apple_vision import AppleVisionOCRProvider
from teach_a_skill.perception.ocr.base import OCRProvider
from teach_a_skill.perception.ocr.mock import MockOCRProvider
from teach_a_skill.perception.ocr.registry import get_ocr_provider
from teach_a_skill.perception.ocr.tesseract import TesseractOCRProvider

__all__ = [
    "OCRProvider",
    "AppleVisionOCRProvider",
    "TesseractOCRProvider",
    "MockOCRProvider",
    "get_ocr_provider",
]
