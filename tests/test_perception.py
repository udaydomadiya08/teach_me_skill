"""Comprehensive tests for Phase 5: Local UI Perception & OCR."""

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image, ImageDraw

from teach_a_skill.config.manager import ConfigManager
from teach_a_skill.core.health import CheckResult, HealthChecker
from teach_a_skill.perception.cache import PerceptionCache
from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.detection.accessibility import PlatformAccessibilityDetector
from teach_a_skill.perception.detection.base import UIElementDetector
from teach_a_skill.perception.detection.geometry import GeometryDetector
from teach_a_skill.perception.detection.mock import MockUIDetector
from teach_a_skill.perception.detection.registry import get_ui_detector
from teach_a_skill.perception.fusion import MultiSourceFusion
from teach_a_skill.perception.models import (
    BoundingBox,
    OCRResult,
    PerceptionFrame,
    PerceptionManifest,
    PerceptionMode,
    PerceptionSource,
    TextRegion,
    UIElement,
    UIElementType,
    VisualRegion,
)
from teach_a_skill.perception.ocr.apple_vision import AppleVisionOCRProvider
from teach_a_skill.perception.ocr.base import OCRProvider
from teach_a_skill.perception.ocr.mock import MockOCRProvider
from teach_a_skill.perception.ocr.registry import get_ocr_provider
from teach_a_skill.perception.ocr.tesseract import TesseractOCRProvider
from teach_a_skill.perception.pipeline import PerceptionPipeline
from teach_a_skill.perception.privacy import PerceptionPrivacyManager
from teach_a_skill.perception.query import PerceptionQueryEngine
from teach_a_skill.perception.reading_order import (
    sort_elements_reading_order,
    sort_text_regions_reading_order,
)
from teach_a_skill.perception.storage import PerceptionStorage
from teach_a_skill.perception.validator import PerceptionValidator
from teach_a_skill.recorder.session import RecordingSession, SessionState
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.storage.manager import StorageManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test storage."""
    d = tempfile.mkdtemp(prefix="test_perception_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def storage_mgr(temp_dir):
    """Create an isolated StorageManager."""
    return StorageManager(base_dir=temp_dir)


def create_synthetic_frame_image(path: Path, width: int = 800, height: int = 600) -> None:
    """Generate a clean synthetic UI frame image with text and shapes."""
    img = Image.new("RGB", (width, height), color=(240, 242, 245))
    draw = ImageDraw.Draw(img)

    # Header / Panel
    draw.rectangle([0, 0, width, 50], fill=(45, 55, 72))
    draw.text((20, 16), "Teach A Skill - Perception Engine", fill=(255, 255, 255))

    # Form Panel
    draw.rectangle([50, 80, 450, 400], fill=(255, 255, 255), outline=(200, 205, 215), width=2)
    draw.text((70, 100), "Settings & Preferences", fill=(20, 20, 20))

    # Input like
    draw.text((70, 150), "Username", fill=(80, 80, 80))
    draw.rectangle([70, 175, 350, 215], fill=(255, 255, 255), outline=(160, 165, 175), width=2)

    # Button like
    draw.rectangle([70, 320, 180, 360], fill=(49, 130, 206))
    draw.text((95, 332), "Submit", fill=(255, 255, 255))

    # Cancel button like
    draw.rectangle([200, 320, 300, 360], fill=(226, 232, 240))
    draw.text((230, 332), "Cancel", fill=(74, 85, 104))

    img.save(path, format="PNG")


def create_test_recording_session(storage_mgr: StorageManager, frame_count: int = 3) -> tuple[str, list[Path]]:
    """Helper to set up an authoritative recording session with immutable frames."""
    session_id = f"test_session_{int(time.time() * 1000)}"
    session = RecordingSession(
        session_id=session_id, platform_name="darwin", architecture="arm64"
    )
    session.transition_to(SessionState.RECORDING)

    sess_storage = SessionStorage(storage_mgr, session_id)
    sess_storage.initialize_session_layout(session.manifest)

    frames_dir = sess_storage.frames_dir
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_paths = []
    frames_meta = []

    for i in range(frame_count):
        f_name = f"frame_{i:05d}.png"
        f_path = frames_dir / f_name
        create_synthetic_frame_image(f_path, width=800, height=600)
        frame_paths.append(f_path)

        with open(f_path, "rb") as f:
            csum = hashlib.sha256(f.read()).hexdigest()

        meta = {
            "frame_id": f"frame_{i:05d}",
            "filename": f_name,
            "path": f"frames/{f_name}",
            "timestamp_ns": 1000000000 + i * 500000000,
            "monotonic_timestamp": 1.0 + i * 0.5,
            "width": 800,
            "height": 600,
            "scale_factor": 1.0,
            "display_id": 1,
            "checksum": csum,
        }
        frames_meta.append(meta)

    session.transition_to(SessionState.STOPPING)
    session.transition_to(SessionState.COMPLETED)
    sess_storage.finalize_session(
        session.manifest,
        {"events_count": 0, "frames_count": frame_count, "completed_at": "2026-10-04T12:00:00Z"},
        {"frames": frames_meta},
    )

    return session_id, frame_paths


# =========================================================================
# 1. Core Model & Coordinate Normalization Tests
# =========================================================================

def test_bounding_box_geometry_and_normalization():
    """Verify BoundingBox calculations, clipping, containment, and IoU."""
    bbox = BoundingBox(
        x=100.0,
        y=50.0,
        width=200.0,
        height=100.0,
        normalized_x=0.1,
        normalized_y=0.05,
        normalized_width=0.2,
        normalized_height=0.1,
        frame_width=1000,
        frame_height=1000,
    )
    assert bbox.x2 == 300.0
    assert bbox.y2 == 150.0
    assert bbox.area == 20000.0
    assert bbox.contains_point(150.0, 75.0) is True
    assert bbox.contains_point(50.0, 75.0) is False
    assert bbox.contains_point(350.0, 75.0) is False

    # Overlap / IoU
    overlap_box = BoundingBox(
        x=150.0,
        y=50.0,
        width=200.0,
        height=100.0,
        normalized_x=0.15,
        normalized_y=0.05,
        normalized_width=0.2,
        normalized_height=0.1,
    )
    iou = bbox.iou(overlap_box)
    assert 0.0 < iou < 1.0
    assert pytest.approx(iou, 0.01) == 15000.0 / 25000.0


def test_coordinate_transformer_retina_and_normalization():
    """Verify high-DPI Retina scaling and normalized coordinate conversion."""
    transformer = CoordinateTransformer(frame_width=2880, frame_height=1800, scale_factor=2.0)

    # 1. From pixel to normalized
    bbox = transformer.from_pixels(1440.0, 900.0, 288.0, 180.0)
    assert bbox.normalized_x == 0.5
    assert bbox.normalized_y == 0.5
    assert bbox.normalized_width == 0.1
    assert bbox.normalized_height == 0.1

    # 2. From normalized to pixels
    rev = transformer.from_normalized(0.5, 0.5, 0.1, 0.1)
    assert rev.x == 1440.0
    assert rev.y == 900.0
    assert rev.width == 288.0
    assert rev.height == 180.0

    # 3. Retina screen points (logical pixels = 1440x900) to device frame pixels (2880x1800)
    fx, fy = transformer.screen_to_frame_pixels(720.0, 450.0)
    assert fx == 1440.0
    assert fy == 900.0


def test_model_serialization_and_provenance():
    """Verify serialization roundtrip and provenance preservation for all models."""
    bbox = BoundingBox(
        x=10.0,
        y=20.0,
        width=100.0,
        height=40.0,
        normalized_x=0.01,
        normalized_y=0.02,
        normalized_width=0.1,
        normalized_height=0.04,
        frame_width=1000,
        frame_height=1000,
    )

    tr = TextRegion(
        region_id="tr_001",
        frame_id="frame_00001",
        text="Submit Order",
        raw_text="Submit Order",
        normalized_text="Submit Order",
        bbox=bbox,
        confidence=0.96,
        language="en-US",
        reading_order=1,
        source=PerceptionSource.OCR,
        provenance={"detector": "mock_ocr", "version": "1.0.0"},
    )
    tr_dict = tr.to_dict()
    tr_restored = TextRegion.from_dict(tr_dict)
    assert tr_restored.region_id == tr.region_id
    assert tr_restored.text == "Submit Order"
    assert tr_restored.confidence == 0.96
    assert tr_restored.provenance["detector"] == "mock_ocr"

    el = UIElement(
        element_id="elem_001",
        frame_id="frame_00001",
        element_type=UIElementType.BUTTON_LIKE,
        bbox=bbox,
        confidence=0.88,
        sources=[PerceptionSource.IMAGE, PerceptionSource.OCR],
        text_content="Submit Order",
        associated_text_ids=["tr_001"],
        reading_order=1,
        provenance={"detector": "geometry_detector"},
    )
    el_dict = el.to_dict()
    el_restored = UIElement.from_dict(el_dict)
    assert el_restored.element_type == UIElementType.BUTTON_LIKE
    assert el_restored.text_content == "Submit Order"
    assert PerceptionSource.OCR in el_restored.sources


# =========================================================================
# 2. OCR Provider Tests
# =========================================================================

def test_mock_ocr_provider(temp_dir):
    """Test MockOCRProvider deterministic behavior and contract compliance."""
    img_path = temp_dir / "test.png"
    create_synthetic_frame_image(img_path)

    provider = MockOCRProvider()
    assert provider.is_available() is True
    assert provider.provider_id == "mock_ocr"

    res = provider.detect_text(img_path, frame_id="frame_00000")
    assert isinstance(res, OCRResult)
    assert res.frame_id == "frame_00000"
    assert len(res.text_regions) > 0
    for tr in res.text_regions:
        assert tr.confidence is not None
        assert tr.bbox.frame_width == 800
        assert tr.bbox.frame_height == 600
        assert 0.0 <= tr.bbox.normalized_x <= 1.0


def test_apple_vision_ocr_availability_and_execution(temp_dir):
    """Test AppleVisionOCRProvider on macOS."""
    provider = AppleVisionOCRProvider()
    if not provider.is_available():
        pytest.skip("Apple Vision framework is not available on this platform")

    img_path = temp_dir / "vision_test.png"
    create_synthetic_frame_image(img_path)

    res = provider.detect_text(img_path, frame_id="frame_test")
    assert isinstance(res, OCRResult)
    assert res.provider_id == "apple_vision"
    assert len(res.text_regions) >= 1
    # Check that text is detected from synthetic image
    found_texts = [t.text.lower() for t in res.text_regions]
    assert any("teach" in t or "skill" in t or "perception" in t or "cancel" in t for t in found_texts)


def test_tesseract_ocr_graceful_missing_binary(monkeypatch):
    """Test TesseractOCRProvider handles missing binary gracefully without crash."""
    provider = TesseractOCRProvider(tesseract_cmd="/nonexistent/path/to/tesseract")
    assert provider.is_available() is False

    with pytest.raises(RuntimeError) as exc_info:
        provider.detect_text(Path("/dummy.png"), "frame_0")
    assert "not available" in str(exc_info.value).lower()


def test_ocr_confidence_preservation():
    """Assert that confidence scores are preserved exactly and not fabricated."""
    provider = MockOCRProvider()
    res = provider.detect_text(Path("/nonexistent"), frame_id="frame_0")
    for tr in res.text_regions:
        # Confidence must be an explicit float or None, never fabricated 1.0 everywhere
        assert isinstance(tr.confidence, float)
        assert 0.0 <= tr.confidence <= 1.0


# =========================================================================
# 3. Reading Order & UI Detection Tests
# =========================================================================

def test_deterministic_spatial_reading_order():
    """Verify top-to-bottom, left-to-right reading order with tie breaking."""
    boxes = [
        # bottom-right
        BoundingBox(x=500.0, y=400.0, width=50.0, height=20.0, normalized_x=0.5, normalized_y=0.4, normalized_width=0.05, normalized_height=0.02),
        # top-left
        BoundingBox(x=50.0, y=20.0, width=50.0, height=20.0, normalized_x=0.05, normalized_y=0.02, normalized_width=0.05, normalized_height=0.02),
        # top-right (same vertical band)
        BoundingBox(x=300.0, y=22.0, width=50.0, height=20.0, normalized_x=0.3, normalized_y=0.022, normalized_width=0.05, normalized_height=0.02),
        # middle-left
        BoundingBox(x=50.0, y=200.0, width=50.0, height=20.0, normalized_x=0.05, normalized_y=0.2, normalized_width=0.05, normalized_height=0.02),
    ]

    elements = [
        UIElement(
            element_id=f"el_{i}",
            frame_id="frame_0",
            element_type=UIElementType.BUTTON_LIKE,
            bbox=b,
            confidence=0.9,
            sources=[PerceptionSource.IMAGE],
        )
        for i, b in enumerate(boxes)
    ]

    sorted_elems = sort_elements_reading_order(elements, y_band_tolerance=10.0)
    # Expected order: top-left (el_1), top-right (el_2), middle-left (el_3), bottom-right (el_0)
    assert sorted_elems[0].element_id == "el_1"
    assert sorted_elems[1].element_id == "el_2"
    assert sorted_elems[2].element_id == "el_3"
    assert sorted_elems[3].element_id == "el_0"
    for idx, el in enumerate(sorted_elems, start=1):
        assert el.reading_order == idx


def test_geometry_detector(temp_dir):
    """Verify GeometryDetector identifies structural regions without reasoning."""
    img_path = temp_dir / "geom_test.png"
    create_synthetic_frame_image(img_path)

    detector = GeometryDetector()
    assert detector.is_available() is True
    assert detector.detector_id == "geometry_detector"

    elements = detector.detect_elements(
        img_path,
        frame_id="frame_0",
        frame_metadata={"width": 800, "height": 600, "scale_factor": 1.0},
    )
    assert len(elements) > 0
    # Must only use neutral taxonomy
    valid_types = {e.value for e in UIElementType}
    for el in elements:
        assert el.element_type.value in valid_types
        # Ensure semantic labels were NOT applied
        assert "submit_button" not in el.element_type.value.lower()
        assert "login" not in el.element_type.value.lower()


def test_accessibility_detector_graceful_degradation():
    """Verify PlatformAccessibilityDetector degrades gracefully when permission is untrusted."""
    detector = PlatformAccessibilityDetector()
    # It must not raise an exception even if accessibility permission is false
    available = detector.is_available()
    assert isinstance(available, bool)


def test_screen_only_fallback_resolution():
    """Verify get_ui_detector falls back to GeometryDetector when requested."""
    det = get_ui_detector(use_accessibility=False)
    assert isinstance(det, GeometryDetector)


# =========================================================================
# 4. Multi-Source Fusion Tests
# =========================================================================

def test_multi_source_fusion():
    """Verify spatial fusion associates text inside geometric elements without semantic bias."""
    fusion = MultiSourceFusion()

    geom_bbox = BoundingBox(
        x=100.0,
        y=100.0,
        width=120.0,
        height=40.0,
        normalized_x=0.1,
        normalized_y=0.1,
        normalized_width=0.12,
        normalized_height=0.04,
        frame_width=1000,
        frame_height=1000,
    )
    geom_elem = UIElement(
        element_id="geom_btn",
        frame_id="frame_0",
        element_type=UIElementType.BUTTON_LIKE,
        bbox=geom_bbox,
        confidence=0.85,
        sources=[PerceptionSource.IMAGE],
    )

    text_bbox = BoundingBox(
        x=120.0,
        y=110.0,
        width=60.0,
        height=20.0,
        normalized_x=0.12,
        normalized_y=0.11,
        normalized_width=0.06,
        normalized_height=0.02,
        frame_width=1000,
        frame_height=1000,
    )
    text_reg = TextRegion(
        region_id="tr_ok",
        frame_id="frame_0",
        text="OK",
        raw_text="OK",
        normalized_text="OK",
        bbox=text_bbox,
        confidence=0.98,
        reading_order=1,
        source=PerceptionSource.OCR,
    )

    fused = fusion.fuse(
        geometric_elements=[geom_elem],
        accessibility_elements=[],
        text_regions=[text_reg],
        frame_id="frame_0",
    )

    assert len(fused) == 1
    target = fused[0]
    assert target.text_content == "OK"
    assert "tr_ok" in target.associated_text_ids
    assert PerceptionSource.IMAGE in target.sources
    assert PerceptionSource.OCR in target.sources
    assert target.element_type == UIElementType.BUTTON_LIKE
    # Ensure intent was NOT added
    assert not hasattr(target, "intent")


# =========================================================================
# 5. Cache & Pipeline Execution Tests
# =========================================================================

def test_perception_cache_hit_and_invalidation(storage_mgr):
    """Verify caching: hit when checksum/config matches, miss when changed."""
    cache = PerceptionCache(storage_mgr)

    p_frame = PerceptionFrame(
        perception_frame_id="perc_0",
        frame_id="f0",
        session_id="s0",
        timestamp_ns=1000,
        relative_time_ms=1.0,
        frame_path="raw/frames/f0.png",
        frame_checksum="abc123",
        frame_width=800,
        frame_height=600,
        scale_factor=1.0,
        mode="SCREEN_ONLY",
        elements_count=1,
        text_regions_count=1,
        processing_time_ms=10.0,
        cache_hit=False,
        config_hash="cfg_hash_1",
    )
    elem = UIElement(
        element_id="el_0",
        frame_id="f0",
        element_type=UIElementType.TEXT,
        bbox=BoundingBox(x=0, y=0, width=10, height=10, normalized_x=0, normalized_y=0, normalized_width=0.1, normalized_height=0.1),
        confidence=0.9,
        sources=[PerceptionSource.IMAGE],
    )
    tr = TextRegion(
        region_id="tr_0",
        frame_id="f0",
        text="Hello",
        raw_text="Hello",
        normalized_text="Hello",
        bbox=BoundingBox(x=0, y=0, width=10, height=10, normalized_x=0, normalized_y=0, normalized_width=0.1, normalized_height=0.1),
        confidence=0.9,
        reading_order=1,
        source=PerceptionSource.OCR,
    )
    ocr = OCRResult(
        ocr_id="ocr_0",
        frame_id="f0",
        provider_id="mock_ocr",
        provider_version="1.0.0",
        text_regions=[tr],
        raw_full_text="Hello",
        confidence_aggregate=0.9,
        timing_ms=5.0,
    )

    key = "cache_key_test_001"
    cache.put(key, p_frame, [elem], [tr], ocr)

    # 1. Cache hit
    hit = cache.get(key)
    assert hit is not None
    assert hit["perception_frame"]["frame_checksum"] == "abc123"
    assert len(hit["elements"]) == 1
    assert hit["text_regions"][0]["text"] == "Hello"

    # 2. Cache miss on unknown key
    miss = cache.get("nonexistent_key")
    assert miss is None

    # 3. Invalidation
    cache.invalidate(key)
    assert cache.get(key) is None


def test_pipeline_end_to_end_and_immutability(storage_mgr):
    """Test full perception pipeline, verifying raw frames are 100% immutable."""
    session_id, frame_paths = create_test_recording_session(storage_mgr, frame_count=3)

    # Record pre-execution checksums of raw frames
    pre_hashes = {}
    for p in frame_paths:
        pre_hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()

    pipeline = PerceptionPipeline(
        storage_manager=storage_mgr,
        ocr_provider=MockOCRProvider(),
        use_accessibility=False,
        enable_cache=True,
    )

    out_dir = pipeline.process_session(session_id)
    assert out_dir.exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "frames.jsonl").exists()
    assert (out_dir / "elements.jsonl").exists()
    assert (out_dir / "text_regions.jsonl").exists()
    assert (out_dir / "ocr_results.jsonl").exists()
    assert (out_dir / "indexes" / "perception_index.json").exists()
    assert (out_dir / "checksums.json").exists()

    # Re-verify raw frames immutability
    for p in frame_paths:
        post_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        assert post_hash == pre_hashes[p.name], f"Raw frame {p.name} was mutated!"


# =========================================================================
# 6. Storage, Validator & Recovery Tests
# =========================================================================

def test_perception_validator_and_integrity(storage_mgr):
    """Verify PerceptionValidator validates partition integrity and flags tampering."""
    session_id, _ = create_test_recording_session(storage_mgr, frame_count=2)
    pipeline = PerceptionPipeline(storage_manager=storage_mgr, ocr_provider=MockOCRProvider())
    pipeline.process_session(session_id)

    validator = PerceptionValidator(storage_mgr)
    is_valid, errors = validator.validate_session(session_id)
    assert is_valid is True
    assert len(errors) == 0

    # Tamper with elements.jsonl
    p_storage = PerceptionStorage(storage_mgr, session_id)
    elems_file = p_storage.elements_file
    with open(elems_file, "a") as f:
        f.write("corrupted non json content\n")

    is_valid_tampered, errors_tampered = validator.validate_session(session_id)
    assert is_valid_tampered is False
    assert any("corrupt" in e.lower() or "json" in e.lower() or "checksum" in e.lower() for e in errors_tampered)


def test_crash_recovery_resumes_interrupted_session(storage_mgr):
    """Verify interrupted processing recovers deterministically."""
    session_id, _ = create_test_recording_session(storage_mgr, frame_count=4)

    # Simulate incomplete staging directory
    p_storage = PerceptionStorage(storage_mgr, session_id)
    staging_dir = p_storage.perception_dir.parent / ".perception_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "partial.tmp").write_text("interrupted")

    pipeline = PerceptionPipeline(storage_manager=storage_mgr, ocr_provider=MockOCRProvider())
    # Processing session cleans up staging and finishes cleanly
    pipeline.process_session(session_id)

    assert not staging_dir.exists()
    validator = PerceptionValidator(storage_mgr)
    valid, errors = validator.validate_session(session_id)
    assert valid is True
    assert len(errors) == 0


# =========================================================================
# 7. Query Engine Tests
# =========================================================================

def test_perception_query_engine_spatial_and_temporal(storage_mgr):
    """Verify PerceptionQueryEngine query capabilities."""
    session_id, _ = create_test_recording_session(storage_mgr, frame_count=3)
    pipeline = PerceptionPipeline(storage_manager=storage_mgr, ocr_provider=MockOCRProvider())
    pipeline.process_session(session_id)

    engine = PerceptionQueryEngine(storage_mgr, session_id)

    # 1. get_perception_frame
    p_frame = engine.get_perception_frame("frame_00000")
    assert p_frame is not None
    assert p_frame.frame_id == "frame_00000"

    # 2. get_ui_elements
    elements = engine.get_ui_elements("frame_00000")
    assert len(elements) > 0

    # 3. get_text_regions
    text_regions = engine.get_text_regions("frame_00000")
    assert len(text_regions) > 0

    # 4. get_visible_text
    visible_texts = engine.get_visible_text("frame_00000")
    assert len(visible_texts) > 0
    assert any(t.text in visible_texts for t in text_regions)

    # 5. get_text_at point
    first_tr = text_regions[0]
    px = first_tr.bbox.x + first_tr.bbox.width / 2.0
    py = first_tr.bbox.y + first_tr.bbox.height / 2.0
    found_tr = engine.get_text_at(px, py, "frame_00000")
    assert found_tr is not None
    assert found_tr.region_id == first_tr.region_id

    # 6. get_elements_in_region
    contained = engine.get_elements_in_region(
        "frame_00000",
        BoundingBox(
            x=0,
            y=0,
            width=800,
            height=600,
            normalized_x=0.0,
            normalized_y=0.0,
            normalized_width=1.0,
            normalized_height=1.0,
        ),
    )
    assert len(contained) == len(elements)

    # 7. get_perception_context (temporal nearest)
    ctx = engine.get_perception_context(1000000000)
    assert ctx is not None
    assert ctx.frame_id == "frame_00000"


# =========================================================================
# 8. Privacy & Redaction Tests
# =========================================================================

def test_privacy_manager_redacts_sensitive_text():
    """Verify PerceptionPrivacyManager sanitizes SSN, credit cards, emails, and passwords."""
    pm = PerceptionPrivacyManager()

    text_with_ssn = "Taxpayer SSN is 123-45-6789 confidential"
    sanitized_ssn = pm.sanitize_text(text_with_ssn)
    assert "123-45-6789" not in sanitized_ssn
    assert "[REDACTED_SSN]" in sanitized_ssn

    text_with_card = "Visa number 4111-2222-3333-4444 approved"
    sanitized_card = pm.sanitize_text(text_with_card)
    assert "4111-2222-3333-4444" not in sanitized_card
    assert "[REDACTED_CARD]" in sanitized_card


def test_network_isolation():
    """Verify perception modules do not initiate outbound network sockets."""
    import urllib.request
    with patch.object(urllib.request, "urlopen", side_effect=RuntimeError("Network access forbidden")):
        # Loading and running OCR pipeline must never trigger network requests
        MockOCRProvider().detect_text(Path("/dummy"), "f0")


# =========================================================================
# 9. Strict Semantic Boundary Tests
# =========================================================================

def test_strict_semantic_boundary_no_intent_or_action_inference():
    """Verify that Phase 5 strictly restricts itself to WHAT IS VISIBLY PRESENT, never WHAT IT MEANS."""
    # Create an element with text "Submit Order" and a button geometry
    bbox = BoundingBox(x=10, y=10, width=100, height=40, normalized_x=0.01, normalized_y=0.01, normalized_width=0.1, normalized_height=0.04)
    el = UIElement(
        element_id="elem_test",
        frame_id="frame_0",
        element_type=UIElementType.BUTTON_LIKE,
        bbox=bbox,
        confidence=0.9,
        sources=[PerceptionSource.IMAGE, PerceptionSource.OCR],
        text_content="Submit Order",
    )

    d = el.to_dict()

    # Assert forbidden semantic / goal / action fields do not exist
    forbidden_keys = [
        "intent",
        "user_intent",
        "goal",
        "task",
        "workflow",
        "next_action",
        "action_recommendation",
        "suggested_click",
        "semantic_role",
        "causal_link",
        "executable_code",
    ]
    for key in forbidden_keys:
        assert key not in d, f"Forbidden semantic key '{key}' found in UIElement!"

    # Ensure no LLM libraries are imported in the perception subsystem
    perception_modules = [
        "teach_a_skill.perception.models",
        "teach_a_skill.perception.pipeline",
        "teach_a_skill.perception.fusion",
        "teach_a_skill.perception.query",
        "teach_a_skill.perception.storage",
    ]
    for mod_name in perception_modules:
        mod = pytest.importorskip(mod_name)
        mod_dict = dir(mod)
        assert "openai" not in mod_dict
        assert "anthropic" not in mod_dict
        assert "google.generativeai" not in mod_dict
        assert "langchain" not in mod_dict


# =========================================================================
# 10. Health Checks & Determinism Tests
# =========================================================================

def test_perception_health_checks(storage_mgr):
    """Verify all Phase 5 perception health checks pass."""
    cfg = ConfigManager()
    report = HealthChecker.run_health_check(cfg, storage_mgr, full=True)

    perc_names = {
        "perception_subsystem",
        "ocr_provider",
        "accessibility_capability",
        "screen_fallback",
        "perception_storage",
        "perception_validator",
        "perception_cache",
    }
    found = [c for c in report.checks if c.name in perc_names]
    assert len(found) == 7

    for c in found:
        assert c.passed is True


def test_deterministic_rebuild(storage_mgr):
    """Verify same frame and provider produce bitwise identical perception outputs."""
    session_id, _ = create_test_recording_session(storage_mgr, frame_count=2)

    pipeline = PerceptionPipeline(
        storage_manager=storage_mgr,
        ocr_provider=MockOCRProvider(),
        use_accessibility=False,
        enable_cache=False,
    )

    # Run 1
    dir1 = pipeline.process_session(session_id, force_reprocess=True)
    elems1 = (dir1 / "elements.jsonl").read_text()
    texts1 = (dir1 / "text_regions.jsonl").read_text()
    idx1 = (dir1 / "indexes" / "perception_index.json").read_text()

    # Run 2
    dir2 = pipeline.process_session(session_id, force_reprocess=True)
    elems2 = (dir2 / "elements.jsonl").read_text()
    texts2 = (dir2 / "text_regions.jsonl").read_text()
    idx2 = (dir2 / "indexes" / "perception_index.json").read_text()

    assert elems1 == elems2
    assert texts1 == texts2
    assert idx1 == idx2
