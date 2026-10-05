"""Platform accessibility adapter for macOS AXUIElement inspection."""

from pathlib import Path
from typing import Any, Optional, Union

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.detection.base import UIElementDetector
from teach_a_skill.perception.models import (
    PerceptionSource,
    TextRegion,
    UIElement,
    UIElementType,
)

logger = get_logger("teach_a_skill.perception.detection.accessibility")


class PlatformAccessibilityDetector(UIElementDetector):
    """Platform accessibility tree inspector (macOS AXUIElement)."""

    def __init__(self) -> None:
        self._available: Optional[bool] = None

    @property
    def detector_id(self) -> str:
        return "accessibility_detector"

    @property
    def detector_version(self) -> str:
        return "macos-ax-v1"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import ApplicationServices

            self._available = bool(ApplicationServices.AXIsProcessTrusted())
        except Exception:
            self._available = False
        return self._available

    def detect_elements(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        frame_metadata: Optional[dict[str, Any]] = None,
        text_regions: Optional[list[TextRegion]] = None,
    ) -> list[UIElement]:
        if not self.is_available():
            logger.debug("Platform accessibility unavailable or untrusted; falling back.")
            return []

        import ApplicationServices

        elements: list[UIElement] = []
        try:
            # 1. First attempt to resolve frontmost application via NSWorkspace
            app = None
            try:
                from AppKit import NSWorkspace

                front = NSWorkspace.sharedWorkspace().frontmostApplication()
                if front:
                    app = ApplicationServices.AXUIElementCreateApplication(front.processIdentifier())
            except Exception:
                app = None

            # Fallback to system-wide focused application
            if not app:
                sys_wide = ApplicationServices.AXUIElementCreateSystemWide()
                err, app = ApplicationServices.AXUIElementCopyAttributeValue(sys_wide, "AXFocusedApplication", None)
                if err != 0 or not app:
                    return []

            err, windows = ApplicationServices.AXUIElementCopyAttributeValue(app, "AXWindows", None)
            if err != 0 or not windows:
                return []

            frame_w = 1920
            frame_h = 1080
            scale_factor = 1.0
            display_id = None
            if frame_metadata:
                frame_w = int(frame_metadata.get("width", 1920))
                frame_h = int(frame_metadata.get("height", 1080))
                scale_factor = float(frame_metadata.get("scale_factor", 1.0))
                display_id = frame_metadata.get("display_id")

            transformer = CoordinateTransformer(
                frame_width=frame_w,
                frame_height=frame_h,
                scale_factor=scale_factor,
                display_id=display_id,
            )

            # Traverse top window hierarchy
            count = 0
            for win in windows[:3]:
                count = self._traverse_element(win, transformer, frame_id, elements, count, max_depth=3)

        except Exception as e:
            logger.debug(f"Accessibility traversal exception: {e}")

        return elements

    def _traverse_element(
        self,
        ax_elem: Any,
        transformer: CoordinateTransformer,
        frame_id: str,
        results: list[UIElement],
        count: int,
        max_depth: int = 3,
    ) -> int:
        if max_depth <= 0 or count >= 100:
            return count

        import ApplicationServices

        try:
            err, role = ApplicationServices.AXUIElementCopyAttributeValue(ax_elem, "AXRole", None)
            if err == 0 and role:
                # Try getting position and size
                err_pos, pos_val = ApplicationServices.AXUIElementCopyAttributeValue(ax_elem, "AXPosition", None)
                err_size, size_val = ApplicationServices.AXUIElementCopyAttributeValue(ax_elem, "AXSize", None)

                if err_pos == 0 and err_size == 0 and pos_val and size_val:
                    x, y, w, h = 0.0, 0.0, 0.0, 0.0
                    try:
                        ok_p, pt = ApplicationServices.AXValueGetValue(pos_val, ApplicationServices.kAXValueCGPointType, None)
                        if ok_p:
                            x, y = float(pt.x), float(pt.y)
                        ok_s, sz = ApplicationServices.AXValueGetValue(size_val, ApplicationServices.kAXValueCGSizeType, None)
                        if ok_s:
                            w, h = float(sz.width), float(sz.height)
                    except Exception:
                        try:
                            x = float(getattr(pos_val, "x", 0.0))
                            y = float(getattr(pos_val, "y", 0.0))
                            w = float(getattr(size_val, "width", 0.0))
                            h = float(getattr(size_val, "height", 0.0))
                        except Exception:
                            pass

                    if w > 0 and h > 0:
                        count += 1
                        bbox = transformer.from_screen_coordinates(x, y, w, h)
                        el_type = self._map_role_to_type(str(role))

                        err_title, title_val = ApplicationServices.AXUIElementCopyAttributeValue(
                            ax_elem, "AXTitle", None
                        )
                        text_content = str(title_val) if err_title == 0 and title_val else None

                        e_id = f"elem_ax_{count:05d}_{frame_id}"
                        results.append(
                            UIElement(
                                element_id=e_id,
                                frame_id=frame_id,
                                element_type=el_type,
                                bbox=bbox,
                                confidence=1.0,
                                sources=[PerceptionSource.ACCESSIBILITY.value],
                                text_content=text_content,
                                accessibility_attributes={"role": str(role)},
                                reading_order=count,
                                provenance={
                                    "detector": self.detector_id,
                                    "role": str(role),
                                    "frame_id": frame_id,
                                },
                            )
                        )

            # Traverse children
            err_ch, children = ApplicationServices.AXUIElementCopyAttributeValue(ax_elem, "AXChildren", None)
            if err_ch == 0 and children:
                for ch in children[:15]:
                    count = self._traverse_element(ch, transformer, frame_id, results, count, max_depth - 1)

        except Exception:
            pass

        return count

    def _map_role_to_type(self, role: str) -> UIElementType:
        mapping = {
            "AXButton": UIElementType.BUTTON_LIKE,
            "AXTextField": UIElementType.INPUT_LIKE,
            "AXTextArea": UIElementType.INPUT_LIKE,
            "AXCheckBox": UIElementType.CHECKBOX_LIKE,
            "AXRadioButton": UIElementType.RADIO_LIKE,
            "AXPopUpButton": UIElementType.DROPDOWN_LIKE,
            "AXComboBox": UIElementType.DROPDOWN_LIKE,
            "AXImage": UIElementType.IMAGE,
            "AXStaticText": UIElementType.TEXT,
            "AXWindow": UIElementType.WINDOW_REGION,
            "AXGroup": UIElementType.CONTAINER,
            "AXScrollArea": UIElementType.PANEL,
        }
        return mapping.get(role, UIElementType.UNKNOWN_REGION)
