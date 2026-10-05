"""Safety, immutability, candidate integrity, and prompt-injection defense validator."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from teach_a_skill.learning.models import CandidateSkillVersion


class LearningValidator:
    """Enforces non-execution boundaries, prompt injection defense, and anti-self-modification rules."""

    FORBIDDEN_INJECTION_TOKENS = [
        "rm -rf",
        "sudo ",
        "eval(",
        "exec(",
        "__import__",
        "subprocess.Popen",
        "chmod 777",
        "disable safety",
        "bypass policy",
        "grant permission",
    ]

    @classmethod
    def validate_candidate_safety(cls, candidate: CandidateSkillVersion) -> tuple[bool, str]:
        """Verify candidate integrity, non-tampering, and dangerous token absence."""
        # 1. Cryptographic fingerprint check
        serialized_ir = json.dumps(candidate.skill_ir, sort_keys=True, default=str, separators=(",", ":"))
        actual_fp = hashlib.sha256(serialized_ir.encode("utf-8")).hexdigest()
        if actual_fp != candidate.fingerprint:
            return False, f"Candidate integrity failure: fingerprint mismatch (expected {candidate.fingerprint}, got {actual_fp})"

        # 2. Forbidden command token check
        full_content = (str(candidate.diff) + " " + str(candidate.skill_ir)).lower()
        for token in cls.FORBIDDEN_INJECTION_TOKENS:
            if token in full_content:
                return False, f"Forbidden injection token detected in candidate: '{token}'"

        return True, "Candidate validated: integrity and safety constraints satisfied"

    @classmethod
    def validate_prompt_injection(cls, raw_text: str) -> tuple[bool, str]:
        """Detect prompt injection attempts in recorded user or application execution content."""
        lower = raw_text.lower()
        injection_phrases = [
            "ignore previous instructions",
            "disable safety",
            "disable execution policy",
            "you are now an admin",
            "delete all skills",
            "change your safety policy",
            "execute shell",
            "bypasstoken",
            "bypasssafetypolicy",
            "safety bypass",
            "permission_level",
            "unrestricted",
            "system prompt",
        ]
        for phrase in injection_phrases:
            if phrase in lower:
                return False, f"Prompt injection pattern detected: '{phrase}'. Content rejected."

        return True, "No prompt injection patterns detected"

    @classmethod
    def validate_proposal_payload(cls, payload: dict[str, Any]) -> tuple[bool, str]:
        """Enforce strict safety boundary: proposals must never execute code, shell commands, or escalate privileges."""
        p_type = str(payload.get("type", "")).lower()
        forbidden_types = {
            "execute_code",
            "code_execution",
            "shell_command",
            "grant_permission",
            "network_call",
            "modify_safety_policy",
            "arbitrary_execution",
        }
        if p_type in forbidden_types:
            return False, f"Forbidden proposal action type '{p_type}'. Safety policy violation."

        serialized = json.dumps(payload, default=str).lower()
        for token in cls.FORBIDDEN_INJECTION_TOKENS:
            if token in serialized:
                return False, f"Forbidden keyword '{token}' detected in proposal payload."

        return True, "Proposal payload complies with safety boundary"

    @classmethod
    def validate_version_immutability(
        cls,
        base_ir_before: dict[str, Any],
        base_ir_after: dict[str, Any],
    ) -> tuple[bool, str]:
        """Ensure original base version was not mutated in place."""
        fp1 = hashlib.sha256(json.dumps(base_ir_before, sort_keys=True, default=str).encode()).hexdigest()
        fp2 = hashlib.sha256(json.dumps(base_ir_after, sort_keys=True, default=str).encode()).hexdigest()
        if fp1 != fp2:
            return False, "Base SkillVersion was illegally modified in place! Immutability violated."
        return True, "Base SkillVersion immutability strictly preserved"
