"""Semantic grounding engine: resolves Skill IR targets to live UI elements.

Uses a multi-strategy cascade:
1. Accessibility label matching
2. OCR text matching
3. UI role matching
4. Window/application matching
5. Visual region matching
6. Combined/semantic context matching

Each strategy produces GroundingCandidates. The best candidate
is selected based on confidence ranking and disambiguation rules.
"""

from __future__ import annotations

import logging
import time
import uuid
from difflib import SequenceMatcher
from typing import Any, Optional

from teach_a_skill.execution.models import (
    EnvironmentElement,
    EnvironmentSnapshot,
    GroundingCandidate,
    GroundingMatchType,
    GroundingResult,
)
from teach_a_skill.skill.models import GroundingRequirement, GroundingStrategy, SkillStep

logger = logging.getLogger(__name__)

# Minimum confidence to consider a candidate valid
MIN_GROUNDING_CONFIDENCE = 0.3

# Threshold above which grounding is considered reliable
RELIABLE_GROUNDING_THRESHOLD = 0.7

# Maximum candidates to return per step
MAX_CANDIDATES = 10

# Strategy mapping from Skill IR to execution grounding
STRATEGY_MAP: dict[GroundingStrategy, GroundingMatchType] = {
    GroundingStrategy.ACCESSIBILITY: GroundingMatchType.ACCESSIBILITY,
    GroundingStrategy.OCR_TEXT: GroundingMatchType.OCR_TEXT,
    GroundingStrategy.UI_ROLE: GroundingMatchType.UI_ROLE,
    GroundingStrategy.WINDOW: GroundingMatchType.WINDOW,
    GroundingStrategy.APPLICATION: GroundingMatchType.APPLICATION,
    GroundingStrategy.VISUAL_REGION: GroundingMatchType.VISUAL_REGION,
    GroundingStrategy.SEMANTIC_CONTEXT: GroundingMatchType.SEMANTIC_CONTEXT,
}


def _text_similarity(a: str, b: str) -> float:
    """Compute normalized text similarity between two strings."""
    if not a or not b:
        return 0.0
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    if a_lower == b_lower:
        return 1.0
    return SequenceMatcher(None, a_lower, b_lower).ratio()


class SemanticGroundingEngine:
    """Multi-strategy semantic grounding from Skill IR to live environment."""

    def __init__(
        self,
        min_confidence: float = MIN_GROUNDING_CONFIDENCE,
        reliable_threshold: float = RELIABLE_GROUNDING_THRESHOLD,
        max_candidates: int = MAX_CANDIDATES,
    ) -> None:
        self.min_confidence = min_confidence
        self.reliable_threshold = reliable_threshold
        self.max_candidates = max_candidates

    def ground_step(
        self,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        grounding_req: Optional[GroundingRequirement] = None,
    ) -> GroundingResult:
        """Ground a single skill step against the live environment snapshot.

        Args:
            step: The Skill IR step with target information.
            snapshot: Current environment snapshot.
            grounding_req: Optional explicit grounding requirement from the Skill IR.

        Returns:
            A GroundingResult with best candidate and all candidates ranked.
        """
        start = time.monotonic()
        target_name = step.target
        req = grounding_req or step.grounding

        # Determine strategy order
        strategies = self._build_strategy_order(req)

        all_candidates: list[GroundingCandidate] = []
        strategies_attempted: list[str] = []

        for strategy in strategies:
            strategies_attempted.append(str(strategy))
            candidates = self._match_strategy(strategy, target_name, step, snapshot, req)
            all_candidates.extend(candidates)

        # Deduplicate and rank
        all_candidates = self._deduplicate_candidates(all_candidates)
        all_candidates.sort(key=lambda c: c.confidence, reverse=True)
        all_candidates = all_candidates[: self.max_candidates]

        # Select best
        best = all_candidates[0] if all_candidates else None
        grounded = best is not None and best.confidence >= self.min_confidence
        ambiguous = (
            len(all_candidates) >= 2
            and all_candidates[0].confidence > 0
            and abs(all_candidates[0].confidence - all_candidates[1].confidence) < 0.1
        )

        elapsed_ms = (time.monotonic() - start) * 1000

        explanation = ""
        if grounded and best:
            explanation = (
                f"Target '{target_name}' grounded via {best.match_type} "
                f"with confidence {best.confidence:.2f}"
            )
            if ambiguous:
                explanation += " (AMBIGUOUS: multiple close candidates)"
        else:
            explanation = f"Target '{target_name}' could not be grounded (no candidates above threshold)"

        return GroundingResult(
            step_id=step.step_id,
            target_name=target_name,
            grounded=grounded,
            best_candidate=best,
            all_candidates=all_candidates,
            confidence=best.confidence if best else 0.0,
            ambiguous=ambiguous,
            explanation=explanation,
            strategies_attempted=strategies_attempted,
            timing_ms=elapsed_ms,
            provenance={
                "snapshot_id": snapshot.snapshot_id,
                "elements_scanned": len(snapshot.elements),
                "candidates_found": len(all_candidates),
            },
        )

    def ground_all_steps(
        self,
        steps: list[SkillStep],
        snapshot: EnvironmentSnapshot,
        grounding_reqs: Optional[list[GroundingRequirement]] = None,
    ) -> list[GroundingResult]:
        """Ground all steps in a skill against the current environment."""
        results: list[GroundingResult] = []
        req_map: dict[str, GroundingRequirement] = {}
        if grounding_reqs:
            for req in grounding_reqs:
                req_map[req.target_name] = req

        for step in steps:
            req = req_map.get(step.target) or step.grounding
            result = self.ground_step(step, snapshot, req)
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Strategy order
    # ------------------------------------------------------------------

    def _build_strategy_order(
        self, req: Optional[GroundingRequirement]
    ) -> list[GroundingMatchType]:
        """Build ordered list of strategies based on grounding requirement."""
        if req:
            primary = STRATEGY_MAP.get(req.preferred_strategy, GroundingMatchType.ACCESSIBILITY)
            fallbacks = [STRATEGY_MAP.get(s, GroundingMatchType.SEMANTIC_CONTEXT) for s in req.fallback_strategies]
            seen = {primary}
            ordered = [primary]
            for fb in fallbacks:
                if fb not in seen:
                    ordered.append(fb)
                    seen.add(fb)
            # Always try remaining strategies
            for mt in GroundingMatchType:
                if mt not in seen and mt != GroundingMatchType.NONE:
                    ordered.append(mt)
            return ordered

        # Default strategy order
        return [
            GroundingMatchType.ACCESSIBILITY,
            GroundingMatchType.OCR_TEXT,
            GroundingMatchType.UI_ROLE,
            GroundingMatchType.WINDOW,
            GroundingMatchType.APPLICATION,
            GroundingMatchType.VISUAL_REGION,
            GroundingMatchType.SEMANTIC_CONTEXT,
            GroundingMatchType.COMBINED,
        ]

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _match_strategy(
        self,
        strategy: GroundingMatchType,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Dispatch to the appropriate matching strategy."""
        dispatch = {
            GroundingMatchType.ACCESSIBILITY: self._match_accessibility,
            GroundingMatchType.OCR_TEXT: self._match_ocr_text,
            GroundingMatchType.UI_ROLE: self._match_ui_role,
            GroundingMatchType.WINDOW: self._match_window,
            GroundingMatchType.APPLICATION: self._match_application,
            GroundingMatchType.VISUAL_REGION: self._match_visual_region,
            GroundingMatchType.SEMANTIC_CONTEXT: self._match_semantic_context,
            GroundingMatchType.COMBINED: self._match_combined,
        }
        fn = dispatch.get(strategy)
        if fn:
            return fn(target_name, step, snapshot, req)
        return []

    def _match_accessibility(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match by accessibility label and role."""
        candidates: list[GroundingCandidate] = []
        for elem in snapshot.elements:
            label = elem.label or ""
            title = elem.title or ""
            # Compare against both label and title
            label_sim = _text_similarity(target_name, label)
            title_sim = _text_similarity(target_name, title)
            best_sim = max(label_sim, title_sim)

            if best_sim >= self.min_confidence:
                candidates.append(
                    GroundingCandidate(
                        candidate_id=f"ax_{elem.element_id}_{uuid.uuid4().hex[:6]}",
                        target_name=target_name,
                        match_type=GroundingMatchType.ACCESSIBILITY,
                        confidence=best_sim,
                        pixel_x=elem.pixel_x,
                        pixel_y=elem.pixel_y,
                        pixel_width=elem.pixel_width,
                        pixel_height=elem.pixel_height,
                        text_content=label or title,
                        element_role=elem.role,
                        application=elem.application,
                        window_title=elem.window_title,
                        accessibility_label=label,
                        provenance={"strategy": "accessibility", "element_id": elem.element_id},
                    )
                )
        return candidates

    def _match_ocr_text(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match by OCR text regions in the snapshot."""
        candidates: list[GroundingCandidate] = []
        for region in snapshot.ocr_text_regions:
            text = region.get("text", "")
            sim = _text_similarity(target_name, text)
            if sim >= self.min_confidence:
                bbox = region.get("bbox", {})
                candidates.append(
                    GroundingCandidate(
                        candidate_id=f"ocr_{region.get('region_id', 'unknown')}_{uuid.uuid4().hex[:6]}",
                        target_name=target_name,
                        match_type=GroundingMatchType.OCR_TEXT,
                        confidence=sim * 0.9,  # Slight penalty for OCR-only
                        pixel_x=bbox.get("x", 0),
                        pixel_y=bbox.get("y", 0),
                        pixel_width=bbox.get("width", 0),
                        pixel_height=bbox.get("height", 0),
                        text_content=text,
                        provenance={"strategy": "ocr_text", "region_id": region.get("region_id")},
                    )
                )
        return candidates

    def _match_ui_role(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match by UI element role type."""
        candidates: list[GroundingCandidate] = []
        expected_role = None
        if req:
            expected_role = req.element_type.lower() if req.element_type else None

        for elem in snapshot.elements:
            role_match = 0.0
            if expected_role and elem.role.lower() == expected_role:
                role_match = 0.4
            elif expected_role and expected_role in elem.role.lower():
                role_match = 0.3

            # Also check text similarity
            label = elem.label or elem.title or ""
            text_sim = _text_similarity(target_name, label) if label else 0.0
            combined = max(role_match, text_sim * 0.7)

            if combined >= self.min_confidence:
                candidates.append(
                    GroundingCandidate(
                        candidate_id=f"role_{elem.element_id}_{uuid.uuid4().hex[:6]}",
                        target_name=target_name,
                        match_type=GroundingMatchType.UI_ROLE,
                        confidence=combined,
                        pixel_x=elem.pixel_x,
                        pixel_y=elem.pixel_y,
                        pixel_width=elem.pixel_width,
                        pixel_height=elem.pixel_height,
                        text_content=label,
                        element_role=elem.role,
                        application=elem.application,
                        provenance={"strategy": "ui_role", "element_id": elem.element_id},
                    )
                )
        return candidates

    def _match_window(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match against window title."""
        candidates: list[GroundingCandidate] = []
        if snapshot.active_window_title:
            sim = _text_similarity(target_name, snapshot.active_window_title)
            if sim >= 0.5:
                confidence = sim * 0.8
                if confidence >= self.min_confidence:
                    candidates.append(
                        GroundingCandidate(
                            candidate_id=f"win_{uuid.uuid4().hex[:8]}",
                            target_name=target_name,
                            match_type=GroundingMatchType.WINDOW,
                            confidence=confidence,
                            window_title=snapshot.active_window_title,
                            application=snapshot.active_application,
                            provenance={"strategy": "window"},
                        )
                    )
        return candidates

    def _match_application(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match against running application names."""
        candidates: list[GroundingCandidate] = []
        for app_name in snapshot.running_applications:
            sim = _text_similarity(target_name, app_name)
            if sim >= 0.5:
                confidence = sim * 0.85
                if confidence >= self.min_confidence:
                    candidates.append(
                        GroundingCandidate(
                            candidate_id=f"app_{uuid.uuid4().hex[:8]}",
                            target_name=target_name,
                            match_type=GroundingMatchType.APPLICATION,
                            confidence=confidence,
                            application=app_name,
                            provenance={"strategy": "application"},
                        )
                    )
        return candidates

    def _match_visual_region(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match by visual region position (coarse spatial lookup)."""
        # Visual region matching requires position data; if no elements have
        # meaningful spatial info, this strategy yields nothing.
        candidates: list[GroundingCandidate] = []
        for elem in snapshot.elements:
            if elem.pixel_width > 0 and elem.pixel_height > 0:
                label = elem.label or elem.title or ""
                sim = _text_similarity(target_name, label) if label else 0.0
                if sim >= self.min_confidence:
                    candidates.append(
                        GroundingCandidate(
                            candidate_id=f"vis_{elem.element_id}_{uuid.uuid4().hex[:6]}",
                            target_name=target_name,
                            match_type=GroundingMatchType.VISUAL_REGION,
                            confidence=sim * 0.75,
                            pixel_x=elem.pixel_x,
                            pixel_y=elem.pixel_y,
                            pixel_width=elem.pixel_width,
                            pixel_height=elem.pixel_height,
                            text_content=label,
                            provenance={"strategy": "visual_region"},
                        )
                    )
        return candidates

    def _match_semantic_context(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Match using semantic context (description, arguments, etc.)."""
        candidates: list[GroundingCandidate] = []
        # Use step description and arguments for broader matching
        description_keywords = set(step.description.lower().split()) if step.description else set()

        for elem in snapshot.elements:
            label = (elem.label or elem.title or "").lower()
            value = (elem.value or "").lower()

            # Check if any keywords match element text
            all_text = f"{label} {value}".split()
            overlap = description_keywords.intersection(all_text)
            if overlap and len(overlap) >= 1:
                conf = min(0.6, len(overlap) / max(1, len(description_keywords)))
                if conf >= self.min_confidence:
                    candidates.append(
                        GroundingCandidate(
                            candidate_id=f"sem_{elem.element_id}_{uuid.uuid4().hex[:6]}",
                            target_name=target_name,
                            match_type=GroundingMatchType.SEMANTIC_CONTEXT,
                            confidence=conf,
                            pixel_x=elem.pixel_x,
                            pixel_y=elem.pixel_y,
                            pixel_width=elem.pixel_width,
                            pixel_height=elem.pixel_height,
                            text_content=elem.label or elem.title,
                            element_role=elem.role,
                            provenance={"strategy": "semantic_context", "keyword_overlap": list(overlap)},
                        )
                    )
        return candidates

    def _match_combined(
        self,
        target_name: str,
        step: SkillStep,
        snapshot: EnvironmentSnapshot,
        req: Optional[GroundingRequirement],
    ) -> list[GroundingCandidate]:
        """Combined multi-signal matching for difficult targets."""
        # The combined strategy does not produce new candidates; it
        # relies on candidates already gathered by other strategies.
        return []

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _deduplicate_candidates(
        self, candidates: list[GroundingCandidate]
    ) -> list[GroundingCandidate]:
        """Remove duplicate candidates pointing to the same element."""
        seen: dict[str, GroundingCandidate] = {}
        for c in candidates:
            key = f"{c.pixel_x:.0f}_{c.pixel_y:.0f}_{c.text_content}_{c.element_role}"
            if key not in seen or c.confidence > seen[key].confidence:
                seen[key] = c
        return list(seen.values())


SemanticGrounder = SemanticGroundingEngine

