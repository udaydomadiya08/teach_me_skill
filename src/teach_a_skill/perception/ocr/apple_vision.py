"""Apple Vision framework native OCR provider for macOS."""

import io
import time
from pathlib import Path
from typing import Any, Optional, Union

from PIL import Image

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.models import OCRResult, TextRegion
from teach_a_skill.perception.ocr.base import OCRProvider

logger = get_logger("teach_a_skill.perception.ocr.apple_vision")


class AppleVisionOCRProvider(OCRProvider):
    """Local OCR engine utilizing Apple's hardware-accelerated Vision.framework."""

    def __init__(self, accurate: bool = True, use_language_correction: bool = True) -> None:
        self.accurate = accurate
        self.use_language_correction = use_language_correction
        self._available: Optional[bool] = None

    @property
    def provider_id(self) -> str:
        return "apple_vision"

    @property
    def provider_version(self) -> str:
        return "apple-vision-v1"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import Foundation
            import Vision

            _ = Vision.VNRecognizeTextRequest.alloc().init()
            self._available = True
        except Exception as e:
            logger.debug(f"Apple Vision unavailable: {e}")
            self._available = False
        return self._available

    def detect_text(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        options: Optional[dict[str, Any]] = None,
    ) -> OCRResult:
        if not self.is_available():
            raise RuntimeError("Apple Vision framework is not available on this platform.")

        import Foundation
        import Vision

        t0 = time.perf_counter()

        # Handle image source and determine dimensions
        temp_file: Optional[Path] = None
        img_path: Path
        w, h = 1920, 1080

        if isinstance(image_input, bytes):
            with Image.open(io.BytesIO(image_input)) as img:
                w, h = img.size
            import tempfile

            temp_file = Path(tempfile.mktemp(suffix=".png"))
            temp_file.write_bytes(image_input)
            img_path = temp_file
        else:
            img_path = Path(image_input)
            if not img_path.exists():
                raise FileNotFoundError(f"Image not found at {img_path}")
            with Image.open(img_path) as img:
                w, h = img.size

        transformer = CoordinateTransformer(frame_width=w, frame_height=h)

        try:
            url = Foundation.NSURL.fileURLWithPath_(str(img_path))
            request = Vision.VNRecognizeTextRequest.alloc().init()

            level = (
                Vision.VNRequestTextRecognitionLevelAccurate
                if self.accurate
                else Vision.VNRequestTextRecognitionLevelFast
            )
            request.setRecognitionLevel_(level)
            request.setUsesLanguageCorrection_(self.use_language_correction)

            handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
            success = handler.performRequests_error_([request], None)

            observations = request.results() if success and request.results() else []
            text_regions: list[TextRegion] = []

            for idx, obs in enumerate(observations):
                top_cand = obs.topCandidates_(1)
                if not top_cand:
                    continue
                cand = top_cand[0]
                text_str = str(cand.string())
                conf = float(cand.confidence())

                # Apple Vision normalized coords: origin at bottom-left
                vbox = obs.boundingBox()
                vx = float(vbox.origin.x)
                vy = float(vbox.origin.y)
                vw = float(vbox.size.width)
                vh = float(vbox.size.height)

                # Convert to top-left normalized
                norm_x = vx
                norm_y = max(0.0, 1.0 - (vy + vh))
                norm_w = vw
                norm_h = vh

                bbox = transformer.create_from_normalized(norm_x, norm_y, norm_w, norm_h)
                r_id = f"txt_v_{idx + 1:04d}_{frame_id}"

                words = text_str.split()
                word_ids = [f"{r_id}_w{w_idx}" for w_idx in range(len(words))]

                text_regions.append(
                    TextRegion(
                        region_id=r_id,
                        frame_id=frame_id,
                        text=text_str,
                        raw_text=text_str,
                        normalized_text=text_str.strip(),
                        bbox=bbox,
                        confidence=round(conf, 4),
                        language="en",
                        line_id=f"line_v_{idx + 1:04d}",
                        word_ids=word_ids,
                        reading_order=idx + 1,
                        source_provider=self.provider_id,
                        provenance={
                            "provider": self.provider_id,
                            "level": "accurate" if self.accurate else "fast",
                            "engine": "AppleVision",
                        },
                    )
                )

            dur_ms = (time.perf_counter() - t0) * 1000.0
            full_text = "\n".join(r.text for r in text_regions)
            conf_avg = (
                round(sum(r.confidence for r in text_regions if r.confidence is not None) / len(text_regions), 4)
                if text_regions
                else None
            )

            return OCRResult(
                ocr_id=f"ocr_v_{frame_id}",
                frame_id=frame_id,
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                text_regions=text_regions,
                raw_full_text=full_text,
                confidence_aggregate=conf_avg,
                timing_ms=round(dur_ms, 2),
                provenance={"provider": self.provider_id, "engine": "Vision.framework"},
            )

        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
