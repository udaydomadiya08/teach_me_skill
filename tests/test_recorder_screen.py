"""Tests for screen frames, PNG encoder, and frame indexing."""

from teach_a_skill.recorder.screen import (
    FrameIndexer,
    ScreenFrame,
    create_solid_color_png,
    encode_raw_rgb_to_png,
)


def test_png_encoder_valid_w3c_chunks():
    width = 16
    height = 16
    # 16x16 red image
    raw_rgb = bytes([255, 0, 0]) * (width * height)
    png_bytes = encode_raw_rgb_to_png(width, height, raw_rgb)

    # 1. Check PNG signature
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # 2. Check essential chunks
    assert b"IHDR" in png_bytes
    assert b"IDAT" in png_bytes
    assert png_bytes.endswith(b"IEND\xaeB`\x82")  # IEND chunk with CRC


def test_create_solid_color_png():
    png = create_solid_color_png(64, 64, r=10, g=20, b=30)
    assert len(png) > 50
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_frame_indexer_event_association():
    indexer = FrameIndexer()

    f1 = ScreenFrame(
        frame_id="frame_000001",
        timestamp="2026-10-04T12:00:00Z",
        monotonic_timestamp=10.0,
        display_id=1,
        width=1920,
        height=1080,
        scale_factor=1.0,
        trigger_reason="session_start",
        triggering_event_id="evt_start",
    )
    f2 = ScreenFrame(
        frame_id="frame_000002",
        timestamp="2026-10-04T12:00:02Z",
        monotonic_timestamp=12.0,
        display_id=1,
        width=1920,
        height=1080,
        scale_factor=1.0,
        trigger_reason="mouse_click",
        triggering_event_id="evt_click_1",
    )

    indexer.register_frame(f1)
    indexer.register_frame(f2)

    # Lookup frame directly associated with click event
    associated = indexer.get_frame_for_event("evt_click_1")
    assert associated is not None
    assert associated["frame_id"] == "frame_000002"
    assert associated["trigger_reason"] == "mouse_click"

    # Temporal lookup: nearest frame before timestamp 11.5
    nearest = indexer.find_nearest_frame_before(11.5)
    assert nearest is not None
    assert nearest["frame_id"] == "frame_000001"

    # Nearest frame after timestamp 12.5
    nearest_after = indexer.find_nearest_frame_before(12.5)
    assert nearest_after["frame_id"] == "frame_000002"

    index_dict = indexer.to_index_dict()
    assert index_dict["total_frames"] == 2
    assert "evt_click_1" in index_dict["event_associations"]
