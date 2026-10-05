"""Mock OCR provider for deterministic testing, offline environments, and benchmarks."""

import io
import time
from pathlib import Path
from typing import Any, Optional, Union

from PIL import Image

from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.models import BoundingBox, OCRResult, TextRegion
from teach_a_skill.perception.ocr.base import OCRProvider


class MockOCRProvider(OCRProvider):
    """Deterministic, zero-dependency OCR provider for tests and reproducible benchmarking."""

    def __init__(
        self,
        canned_texts: Optional[list[tuple[str, tuple[float, float, float, float], float]]] = None,
        available: bool = True,
    ) -> None:
        self._canned_texts = canned_texts
        self._available = available

    @property
    def provider_id(self) -> str:
        return "mock_ocr"

    @property
    def provider_version(self) -> str:
        return "1.0.0-mock"

    def is_available(self) -> bool:
        return self._available

    def detect_text(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        options: Optional[dict[str, Any]] = None,
    ) -> OCRResult:
        if not self._available:
            raise RuntimeError("MockOCRProvider configured as unavailable.")

        t0 = time.perf_counter()

        # Determine frame dimensions from image input
        w, h = 1920, 1080
        try:
            if isinstance(image_input, (str, Path)):
                p = Path(image_input)
                if p.exists():
                    with Image.open(p) as img:
                        w, h = img.size
            elif isinstance(image_input, bytes):
                with Image.open(io.BytesIO(image_input)) as img:
                    w, h = img.size
        except Exception:
            pass

        transformer = CoordinateTransformer(frame_width=w, frame_height=h)

        # Default synthetic entries if none provided
        entries = self._canned_texts
        if entries is None:
            entries = [
                ("File", (20.0, 10.0, 40.0, 20.0), 0.99),
                ("Edit", (70.0, 10.0, 40.0, 20.0), 0.98),
                ("View", (120.0, 10.0, 40.0, 20.0), 0.97),
                ("Help", (170.0, 10.0, 40.0, 20.0), 0.99),
                ("Untitled Document", (200.0, 100.0, 250.0, 30.0), 0.95),
                ("Save", (500.0, 100.0, 80.0, 30.0), 0.94),
                ("Cancel", (600.0, 100.0, 80.0, 30.0), 0.96),
            ]

        text_regions: list[TextRegion] = []
        for idx, (txt, (px, py, pw, ph), conf) in enumerate(entries):
            bbox = transformer.create_bounding_box(px, py, pw, ph)
            r_id = f"txt_{idx + 1:04d}_{frame_id}"
            text_regions.append(
                TextRegion(
                    region_id=r_id,
                    frame_id=frame_id,
                    text=txt,
                    raw_text=txt,
                    normalized_text=txt.strip(),
                    bbox=bbox,
                    confidence=conf,
                    language="en",
                    line_id=f"line_{idx + 1:04d}",
                    word_ids=[f"word_{idx + 1:04d}_{widx}" for widx in range(len(txt.split()))],
                    reading_order=idx + 1,
                    source_provider="mock_ocr",
                    provenance={"mock": True, "frame_id": frame_id},
                )
            )

        full_text = "\n".join(r.text for r in text_regions)
        dur_ms = (time.perf_counter() - t0) * 1000.0

        return OCRResult(
            ocr_id=f"ocr_{frame_id}",
            frame_id=frame_id,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            text_regions=text_regions,
            raw_full_text=full_text,
            confidence_aggregate=round(sum(r.confidence for r in text_regions) / len(text_regions), 4) if text_regions else None,
            timing_ms=round(dur_ms, 2),
            provenance={"provider": self.provider_id, "mock": True},
        )
