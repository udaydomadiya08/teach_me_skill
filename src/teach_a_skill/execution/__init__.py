"""Phase 10: Skill Execution & Semantic Grounding.

Runtime layer that loads compiled Skill IRs, grounds their semantic targets
against the live environment, enforces execution policy and safety boundaries,
and performs controlled step-by-step skill replay with verification.

Fundamental rule: execute only what can be grounded, authorized, and verified.
"""
