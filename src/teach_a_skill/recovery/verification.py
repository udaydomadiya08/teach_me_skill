"""Multi-source verification engine for Phase 11.

Evaluates observed execution outcomes against expected application, window,
UI element state, text content, and semantic postconditions.
Supports cross-source verification (Accessibility, OCR, Application State)
with conflict detection. Evidence is strictly required for any verification.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from teach_a_skill.execution.models import (
    EnvironmentSnapshot,
    ExecutionCheckpoint,
)
from teach_a_skill.recovery.models import UIElementObservation, VerificationResult
from teach_a_skill.skill.models import SkillStep

logger = logging.getLogger(__name__)


class VerificationEngine:
    """Verifies postconditions, application state, and checkpoints against live observations."""

    def __init__(self, confidence_threshold: float = 0.6) -> None:
        self.confidence_threshold = confidence_threshold

    def verify_step_postconditions(
        self,
        step: SkillStep,
        snapshot: Optional[EnvironmentSnapshot],
        ocr_text: Optional[str] = None,
        accessibility_tree: Optional[dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify that step execution achieved its expected environmental state."""
        evidence: dict[str, Any] = {}
        sources: list[str] = []
        confidences: list[float] = []
        matches: list[bool] = []
        conflicts: list[str] = []

        if not snapshot:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                evidence={"error": "no_environment_snapshot_available"},
                source="verification_engine",
                details={"reason": "Cannot verify without live environment snapshot"},
            )

        # 1. Expected Application Verification
        expected_app = step.parameters.get("expected_application") or step.parameters.get("app_name")
        if expected_app:
            app_match = (
                snapshot.active_application is not None
                and expected_app.lower() in snapshot.active_application.lower()
            )
            matches.append(app_match)
            sources.append("application_state")
            confidences.append(1.0 if app_match else 0.0)
            evidence["active_application"] = snapshot.active_application
            evidence["expected_application"] = expected_app
            evidence["application_matched"] = app_match

        # 2. Expected Window Verification
        expected_window = step.parameters.get("expected_window") or step.parameters.get("window_title")
        if expected_window:
            win_match = (
                snapshot.active_window_title is not None
                and expected_window.lower() in snapshot.active_window_title.lower()
            )
            matches.append(win_match)
            sources.append("window_state")
            confidences.append(0.95 if win_match else 0.1)
            evidence["active_window"] = snapshot.active_window_title
            evidence["expected_window"] = expected_window
            evidence["window_matched"] = win_match

        # 3. Target Element / Text Verification via Accessibility Elements
        expected_text = (
            step.parameters.get("expected_text")
            or step.parameters.get("text")
            or step.target_element
        )
        acc_matched = False
        acc_evidence: list[dict[str, Any]] = []

        if expected_text and snapshot.elements:
            exp_lower = str(expected_text).lower()
            for elem in snapshot.elements:
                elem_label = (elem.label or elem.title or "").lower()
                elem_val = (elem.value or "").lower()
                if exp_lower in elem_label or exp_lower in elem_val or (elem_label and elem_label in exp_lower):
                    acc_matched = True
                    acc_evidence.append(
                        {
                            "element_id": elem.element_id,
                            "role": elem.role,
                            "label": elem.label,
                            "title": elem.title,
                            "pixel_x": elem.pixel_x,
                            "pixel_y": elem.pixel_y,
                            "pixel_width": elem.pixel_width,
                            "pixel_height": elem.pixel_height,
                        }
                    )
            sources.append("accessibility")
            confidences.append(0.9 if acc_matched else 0.2)
            evidence["accessibility_matches"] = acc_evidence
            matches.append(acc_matched)

        # 4. Multi-Source OCR Verification (if text was expected)
        ocr_matched: Optional[bool] = None
        if expected_text and ocr_text:
            exp_lower = str(expected_text).lower()
            ocr_matched = exp_lower in ocr_text.lower()
            sources.append("ocr")
            confidences.append(0.85 if ocr_matched else 0.15)
            evidence["ocr_matched"] = ocr_matched

            # Conflict Detection: Accessibility says element exists with high confidence,
            # but OCR shows completely contradictory screen text, or vice-versa
            if acc_matched and not ocr_matched and len(ocr_text.strip()) > 50:
                conflicts.append("Accessibility identified element but OCR text did not contain expected text")
            elif not acc_matched and ocr_matched and len(snapshot.elements) > 5:
                conflicts.append("OCR observed expected text but Accessibility found no matching UI elements")

        # 5. Accessibility Tree Verification (if provided)
        if accessibility_tree and expected_text:
            tree_str = str(accessibility_tree).lower()
            tree_matched = str(expected_text).lower() in tree_str
            sources.append("accessibility_tree")
            confidences.append(0.95 if tree_matched else 0.1)
            evidence["accessibility_tree_matched"] = tree_matched
            matches.append(tree_matched)

        # If no specific criteria were provided in step parameters, verify active window & elements exist
        if not matches:
            has_elements = len(snapshot.elements) > 0 or snapshot.active_application is not None
            matches.append(has_elements)
            sources.append("snapshot_presence")
            confidences.append(0.7 if has_elements else 0.0)
            evidence["elements_count"] = len(snapshot.elements)
            evidence["active_application"] = snapshot.active_application

        # Aggregate confidence & determine verdict
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        all_passed = all(matches) and avg_confidence >= self.confidence_threshold
        has_conflict = len(conflicts) > 0

        # If critical conflict detected, trigger verification failure/escalation
        if has_conflict:
            evidence["conflicts"] = conflicts

        return VerificationResult(
            verified=all_passed and not has_conflict,
            confidence=avg_confidence,
            evidence=evidence,
            source="+".join(sources) if sources else "heuristic",
            details={
                "step_id": step.step_id,
                "matches": matches,
                "conflicts": conflicts,
            },
            conflict_detected=has_conflict,
        )

    def verify_checkpoint(
        self,
        checkpoint: ExecutionCheckpoint,
        current_snapshot: EnvironmentSnapshot,
    ) -> VerificationResult:
        """Verify that live environment conforms to an established checkpoint."""
        snap_data = getattr(checkpoint, "environment_snapshot", None)
        if isinstance(snap_data, EnvironmentSnapshot):
            expected_app = snap_data.active_application
            expected_window = snap_data.active_window_title
        elif isinstance(snap_data, dict):
            expected_app = snap_data.get("active_application")
            expected_window = snap_data.get("active_window_title")
        else:
            expected_app = checkpoint.metadata.get("active_application")
            expected_window = checkpoint.metadata.get("active_window_title")

        app_match = (
            expected_app is None
            or (current_snapshot.active_application is not None and expected_app == current_snapshot.active_application)
        )
        win_match = (
            expected_window is None
            or (current_snapshot.active_window_title is not None and expected_window == current_snapshot.active_window_title)
        )

        evidence: dict[str, Any] = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "expected_app": expected_app,
            "actual_app": current_snapshot.active_application,
            "expected_window": expected_window,
            "actual_window": current_snapshot.active_window_title,
            "app_match": app_match,
            "window_match": win_match,
        }

        verified = app_match and win_match
        confidence = 0.95 if verified else (0.5 if app_match else 0.1)

        return VerificationResult(
            verified=verified,
            confidence=confidence,
            evidence=evidence,
            source="checkpoint_verification",
            details={"completed_step_count": len(checkpoint.completed_steps)},
        )
