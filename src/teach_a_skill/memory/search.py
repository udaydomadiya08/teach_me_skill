"""Deterministic search engine and ranking for persistent Skill Memory.

Supports exact, substring, and multi-dimensional structured queries across skills and versions
without requiring an LLM or cloud services.
"""

from __future__ import annotations

from typing import Any, Optional

from teach_a_skill.memory.models import SearchResult, SkillRecord, SkillStatus
from teach_a_skill.memory.storage import SkillMemoryStorage


class SkillSearchEngine:
    """Executes deterministic structured search across stored skill records."""

    def __init__(self, storage: SkillMemoryStorage) -> None:
        self.storage = storage

    def search(
        self,
        query: str,
        status_filter: Optional[SkillStatus] = None,
        tag_filter: Optional[str] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search stored skills and rank deterministically."""
        norm_query = query.strip().lower()
        results: list[SearchResult] = []

        skill_ids = self.storage.list_skill_ids()

        for sid in skill_ids:
            rec = self.storage.load_skill_record(sid)
            if not rec:
                continue

            if status_filter and rec.status != status_filter:
                continue

            if tag_filter and tag_filter.lower() not in [t.lower() for t in rec.tags]:
                continue

            score = 0.0
            reasons: list[str] = []

            # 1. Exact or partial skill_id / fingerprint match
            if norm_query == sid.lower():
                score += 100.0
                reasons.append("Exact skill ID match")
            elif norm_query in sid.lower():
                score += 30.0
                reasons.append("Substring match in skill ID")

            if norm_query and rec.fingerprint and norm_query in rec.fingerprint.lower():
                score += 80.0
                reasons.append("Fingerprint match")

            # 2. Canonical name
            rec_name_norm = rec.canonical_name.lower()
            if norm_query == rec_name_norm:
                score += 50.0
                reasons.append("Exact name match")
            elif norm_query and norm_query in rec_name_norm:
                score += 25.0
                reasons.append("Substring match in name")

            # 3. Description
            desc_norm = rec.description.lower()
            if norm_query and norm_query in desc_norm:
                score += 15.0
                reasons.append("Query present in description")

            # 4. Tags
            for tag in rec.tags:
                if norm_query and norm_query in tag.lower():
                    score += 20.0
                    reasons.append(f"Tag match: '{tag}'")
                    break

            # 5. Dependencies / Applications
            for dep in rec.dependencies:
                if norm_query and norm_query in dep.lower():
                    score += 15.0
                    reasons.append(f"Dependency match: '{dep}'")
                    break

            # If empty query, return all matching filters with base score
            if not norm_query:
                score = 1.0
                reasons.append("Filter match")

            if score > 0.0:
                results.append(
                    SearchResult(
                        skill_id=rec.skill_id,
                        canonical_name=rec.canonical_name,
                        description=rec.description,
                        current_version=rec.current_version,
                        status=rec.status,
                        score=round(score, 2),
                        reasons=reasons,
                    )
                )

        # Sort deterministically: highest score first, then alphabetical by skill_id
        results.sort(key=lambda r: (-r.score, r.skill_id))
        return results[:limit]
