"""Coordinate system normalization, scaling, and display-relative transformation."""

from typing import Optional, Tuple

from teach_a_skill.perception.models import BoundingBox


class CoordinateTransformer:
    """Deterministic coordinate transformer between pixel, display, and normalized space."""

    def __init__(
        self,
        frame_width: int,
        frame_height: int,
        scale_factor: float = 1.0,
        display_id: Optional[str] = None,
        display_origin: Tuple[int, int] = (0, 0),
    ) -> None:
        self.frame_width = max(1, frame_width)
        self.frame_height = max(1, frame_height)
        self.scale_factor = scale_factor if scale_factor > 0 else 1.0
        self.display_id = display_id
        self.display_origin_x, self.display_origin_y = display_origin

    def create_bounding_box(
        self,
        pixel_x: float,
        pixel_y: float,
        pixel_w: float,
        pixel_h: float,
    ) -> BoundingBox:
        """Create a BoundingBox from raw frame pixel coordinates with normalized coordinates."""
        # Clamp to frame boundary
        clamped_x = max(0.0, min(float(pixel_x), float(self.frame_width)))
        clamped_y = max(0.0, min(float(pixel_y), float(self.frame_height)))
        clamped_w = max(0.0, min(float(pixel_w), float(self.frame_width) - clamped_x))
        clamped_h = max(0.0, min(float(pixel_h), float(self.frame_height) - clamped_y))

        norm_x = round(clamped_x / float(self.frame_width), 6)
        norm_y = round(clamped_y / float(self.frame_height), 6)
        norm_w = round(clamped_w / float(self.frame_width), 6)
        norm_h = round(clamped_h / float(self.frame_height), 6)

        return BoundingBox(
            x=round(clamped_x, 2),
            y=round(clamped_y, 2),
            width=round(clamped_w, 2),
            height=round(clamped_h, 2),
            normalized_x=norm_x,
            normalized_y=norm_y,
            normalized_width=norm_w,
            normalized_height=norm_h,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            display_id=self.display_id,
            scale_factor=self.scale_factor,
        )

    def create_from_normalized(
        self,
        norm_x: float,
        norm_y: float,
        norm_w: float,
        norm_h: float,
    ) -> BoundingBox:
        """Create a BoundingBox from normalized [0, 1] coordinates."""
        norm_x = max(0.0, min(1.0, float(norm_x)))
        norm_y = max(0.0, min(1.0, float(norm_y)))
        norm_w = max(0.0, min(1.0 - norm_x, float(norm_w)))
        norm_h = max(0.0, min(1.0 - norm_y, float(norm_h)))

        px_x = round(norm_x * self.frame_width, 2)
        px_y = round(norm_y * self.frame_height, 2)
        px_w = round(norm_w * self.frame_width, 2)
        px_h = round(norm_h * self.frame_height, 2)

        return BoundingBox(
            x=px_x,
            y=px_y,
            width=px_w,
            height=px_h,
            normalized_x=round(norm_x, 6),
            normalized_y=round(norm_y, 6),
            normalized_width=round(norm_w, 6),
            normalized_height=round(norm_h, 6),
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            display_id=self.display_id,
            scale_factor=self.scale_factor,
        )

    def to_screen_coordinates(self, bbox: BoundingBox) -> Tuple[float, float, float, float]:
        """Convert frame pixel coordinates to display screen coordinates accounting for scaling."""
        screen_x = (bbox.x / self.scale_factor) + self.display_origin_x
        screen_y = (bbox.y / self.scale_factor) + self.display_origin_y
        screen_w = bbox.width / self.scale_factor
        screen_h = bbox.height / self.scale_factor
        return (round(screen_x, 2), round(screen_y, 2), round(screen_w, 2), round(screen_h, 2))

    def from_screen_coordinates(
        self,
        screen_x: float,
        screen_y: float,
        screen_w: float,
        screen_h: float,
    ) -> BoundingBox:
        """Convert display screen coordinates into frame pixel coordinates and BoundingBox."""
        px_x = (screen_x - self.display_origin_x) * self.scale_factor
        px_y = (screen_y - self.display_origin_y) * self.scale_factor
        px_w = screen_w * self.scale_factor
        px_h = screen_h * self.scale_factor
        return self.create_bounding_box(px_x, px_y, px_w, px_h)

    def from_pixels(self, px_x: float, px_y: float, px_w: float, px_h: float) -> BoundingBox:
        """Alias for create_bounding_box."""
        return self.create_bounding_box(px_x, px_y, px_w, px_h)

    def from_normalized(self, norm_x: float, norm_y: float, norm_w: float, norm_h: float) -> BoundingBox:
        """Alias for create_from_normalized."""
        return self.create_from_normalized(norm_x, norm_y, norm_w, norm_h)

    def screen_to_frame_pixels(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """Convert logical screen coordinates to device frame pixel coordinates."""
        px_x = (screen_x - self.display_origin_x) * self.scale_factor
        px_y = (screen_y - self.display_origin_y) * self.scale_factor
        return (round(px_x, 2), round(px_y, 2))
