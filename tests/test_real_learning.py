"""Real-world physical execution test for Phase 13 using safe local TextEdit."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts dir is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_phase13_real import (
    verify_benchmarks_and_scaling,
    verify_real_failure_learning_loop,
    verify_real_harmless_learning,
    verify_real_rollback,
    verify_security_and_boundaries,
)


def test_real_harmless_learning_workflow():
    res = verify_real_harmless_learning()
    assert res["status"] == "PASSED"
    assert res["candidate_version"] == "1.0.1"
    assert res["production_immutable"] is True


def test_real_failure_learning_loop():
    res = verify_real_failure_learning_loop()
    assert res["status"] == "PASSED"
    assert "pattern_detected" in res


def test_real_rollback_workflow():
    res = verify_real_rollback()
    assert res["status"] == "PASSED"
    assert res["promoted_version"] == "1.0.1"
    assert res["regression_detected"] is True
    assert res["restored_version"] == "1.0.0"


def test_security_adversarial_and_injection():
    res = verify_security_and_boundaries()
    assert res["status"] == "PASSED"


def test_benchmarks_and_scaling_runner():
    res = verify_benchmarks_and_scaling()
    assert res["memory_bounded"] is True
    assert res["false_positive_rejected"] is True
    assert res["false_negative_detected"] is True
