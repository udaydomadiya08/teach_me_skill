"""Tesseract local OCR provider using pytesseract and local binaries."""

import io
import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional, Union

from PIL import Image

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.models import OCRResult, TextRegion
from teach_a_skill.perception.ocr.base import OCRProvider

logger = get_logger("teach_a_skill.perception.ocr.tesseract")


class TesseractOCRProvider(OCRProvider):
    """Local Tesseract OCR engine."""

    def __init__(
        self,
        psm: int = 11,
        oem: int = 3,
        lang: str = "eng",
        tesseract_cmd: Optional[str] = None,
    ) -> None:
        self.psm = psm
        self.oem = oem
        self.lang = lang
        self.tesseract_cmd = tesseract_cmd
        self._available: Optional[bool] = None

    @property
    def provider_id(self) -> str:
        return "tesseract"

    @property
    def provider_version(self) -> str:
        return "tesseract-v5"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        cmd = self.tesseract_cmd or "tesseract"
        cmd_path = Path(cmd)
        has_bin = (cmd_path.is_file() and os.access(cmd_path, os.X_OK)) or bool(shutil.which(cmd))
        if not has_bin:
            self._available = False
            return False
        try:
            import pytesseract

            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            _ = pytesseract.get_tesseract_version()
            self._available = True
        except Exception as e:
            logger.debug(f"Tesseract unavailable: {e}")
            self._available = False
        return self._available

    def detect_text(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        options: Optional[dict[str, Any]] = None,
    ) -> OCRResult:
        if not self.is_available():
            raise RuntimeError("Tesseract OCR is not available on this platform.")

        import pytesseract

        t0 = time.perf_counter()

        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input)
        elif isinstance(image_input, bytes):
            img = Image.open(io.BytesIO(image_input))
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        w, h = img.size
        transformer = CoordinateTransformer(frame_width=w, frame_height=h)

        config = f"--oem {self.oem} --psm {self.psm}"
        data = pytesseract.image_to_data(img, lang=self.lang, config=config, output_type=pytesseract.Output.DICT)

        text_regions: list[TextRegion] = []
        n_boxes = len(data["text"])
        region_count = 0

        for i in range(n_boxes):
            word_text = str(data["text"][i]).strip()
            conf_val = float(data["conf"][i])
            if not word_text or conf_val < 0:
                continue

            region_count += 1
            px = float(data["left"][i])
            py = float(data["top"][i])
            pw = float(data["width"][i])
            ph = float(data["height"][i])

            conf_norm = round(max(0.0, min(1.0, conf_val / 100.0)), 4)
            bbox = transformer.create_bounding_box(px, py, pw, ph)
            r_id = f"txt_t_{region_count:04d}_{frame_id}"

            text_regions.append(
                TextRegion(
                    region_id=r_id,
                    frame_id=frame_id,
                    text=word_text,
                    raw_text=word_text,
                    normalized_text=word_text,
                    bbox=bbox,
                    confidence=conf_norm,
                    language=self.lang,
                    line_id=f"line_t_{data['line_num'][i]:04d}",
                    word_ids=[f"{r_id}_w0"],
                    reading_order=region_count,
                    source_provider=self.provider_id,
                    provenance={"provider": self.provider_id, "block_num": data["block_num"][i]},
                )
            )

        dur_ms = (time.perf_counter() - t0) * 1000.0
        full_text = " ".join(r.text for r in text_regions)
        conf_avg = (
            round(sum(r.confidence for r in text_regions if r.confidence is not None) / len(text_regions), 4)
            if text_regions
            else None
        )

        return OCRResult(
            ocr_id=f"ocr_t_{frame_id}",
            frame_id=frame_id,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            text_regions=text_regions,
            raw_full_text=full_text,
            confidence_aggregate=conf_avg,
            timing_ms=round(dur_ms, 2),
            provenance={"provider": self.provider_id, "engine": "Tesseract"},
        )
