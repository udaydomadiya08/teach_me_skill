"""Tests for Phase 15 Production Release validation, SBOM, release manifest, and stress testing."""

import hashlib
import json
from pathlib import Path
import tempfile
import pytest

from teach_a_skill.packaging.manager import PackageManager, PlatformPackage
from teach_a_skill.security.dependencies import DependencyAuditor
from teach_a_skill.security.network import NetworkIsolationMonitor
from teach_a_skill.core.health import HealthChecker
from teach_a_skill.core.config import ConfigManager
from teach_a_skill.storage.manager import StorageManager
from scripts.verify_phase15_production import (
    ProductionReleaseManager,
    CANONICAL_VERSION,
)


def test_production_version_consistency():
    import teach_a_skill
    assert teach_a_skill.__version__ == CANONICAL_VERSION
    assert CANONICAL_VERSION == "1.0.0"


def test_production_sbom_generation(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    sbom_info = rel_mgr.generate_sbom()
    assert Path(sbom_info["path"]).exists()
    assert len(sbom_info["sha256"]) == 64
    assert sbom_info["components_count"] > 0

    with open(sbom_info["path"], "r", encoding="utf-8") as f:
        sbom_data = json.load(f)
    assert sbom_data["bomFormat"] == "CycloneDX"
    assert sbom_data["metadata"]["component"]["version"] == "1.0.0"


def test_release_packages_and_checksums(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    pkg_records = rel_mgr.build_release_packages()
    assert len(pkg_records) >= 4

    sha_file = tmp_path / "release" / "checksums" / "SHA256SUMS"
    assert sha_file.exists()
    sha_content = sha_file.read_text(encoding="utf-8")

    for pkg in pkg_records:
        assert Path(pkg["path"]).exists()
        assert pkg["sha256"] in sha_content


def test_clean_build_reproducibility(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    repro = rel_mgr.verify_clean_build_reproducibility()
    assert repro["reproducible"] is True
    assert repro["build_1_sha256"] == repro["build_2_sha256"]


def test_end_to_end_demonstration_workflow(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    res = rel_mgr.run_end_to_end_demonstration_workflow()
    assert res["status"] == "PASS"
    assert res["provenance_verified"] is True
    assert res["immutable_history_preserved"] is True


def test_determinism_suite(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    det = rel_mgr.verify_determinism_suite(iterations=100)
    assert det["iterations_tested"] == 100
    assert det["nondeterminism_detected"] is False
    assert len(det["deterministic_output_hash"]) == 64


def test_hardware_adaptation_router(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    hw_res = rel_mgr.run_hardware_adaptation_router_test()
    for prof in ("BASELINE", "STANDARD", "HIGH"):
        assert prof in hw_res
        assert hw_res[prof]["offline_verified"] is True
        assert hw_res[prof]["resource_bounded"] is True


def test_large_demonstration_stress(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    large_res = rel_mgr.run_large_demonstration_stress(event_count=1000)  # fast unit test run
    assert large_res["events_processed"] == 1000
    assert large_res["bounded_memory"] is True


def test_skill_registry_scale(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    reg_res = rel_mgr.run_skill_registry_scale_test(skill_count=100)
    assert reg_res["skills_registered"] == 100
    assert reg_res["search_correctness"] is True


def test_concurrent_sessions_isolation(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    iso_res = rel_mgr.run_concurrent_sessions_isolation_test([2, 5])
    assert iso_res["2_sessions"] == "ISOLATED_ZERO_LEAK"
    assert iso_res["5_sessions"] == "ISOLATED_ZERO_LEAK"


def test_crash_recovery_and_backup_restore(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    crash = rel_mgr.run_crash_recovery_resilience_test()
    assert crash["status"] == "PASS"
    assert crash["no_corrupted_canonical_state"] is True

    backup = rel_mgr.run_backup_and_restore_test()
    assert backup["status"] == "PASS"
    assert backup["fingerprints_match"] is True


def test_security_adversarial_regression(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    sec = rel_mgr.run_security_regression_suite()
    assert sec["security_regression"] == "PASS"
    assert sec["status"] == "ALL_VECTORS_BLOCKED"


def test_release_manifest_and_production_checklist(tmp_path):
    rel_mgr = ProductionReleaseManager(tmp_path)
    pkgs = rel_mgr.build_release_packages()
    sbom = rel_mgr.generate_sbom()
    counts = {"passed": 470, "failed": 0, "total": 470}
    benches = {"startup_ms": 12.4}

    manifest = rel_mgr.generate_release_manifest(pkgs, sbom, counts, benches)
    assert manifest["release_version"] == "1.0.0"
    assert len(manifest["manifest_sha256"]) == 64
    assert (tmp_path / "release" / "manifests" / "release_manifest.json").exists()

    checklist = rel_mgr.generate_production_checklist()
    assert all(checklist.values()) is True


def test_placeholder_rejection_integrity(tmp_path):
    """Verify release integrity rejects placeholder, sequential, and synthetic hashes."""
    # Test synthetic and sequential pattern rejection
    bad_patterns = [
        "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
        "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "7c82a1d2f939e6a0d3b68c5b6f7e8a9d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a5f",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    ]
    for bad in bad_patterns:
        is_ph, reason = PackageManager.is_placeholder_or_synthetic_hash(bad)
        assert is_ph is True, f"Failed to detect placeholder: {bad}"

    # Verify real package hashes are accepted
    packages = PackageManager.get_supported_packages()
    for p in packages:
        is_ph, _ = PackageManager.is_placeholder_or_synthetic_hash(p.sha256)
        assert is_ph is False, f"Legitimate package hash flagged: {p.sha256}"


def test_artifact_tampering_detection(tmp_path):
    """Artifact tampering test: copy artifact, flip 1 byte, verify rejection, restore, verify pass."""
    rel_mgr = ProductionReleaseManager(tmp_path)
    pkgs = rel_mgr.build_release_packages()
    assert len(pkgs) > 0

    target_pkg = pkgs[0]
    pkg_file = Path(target_pkg["path"])
    original_bytes = pkg_file.read_bytes()
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    assert original_sha == target_pkg["sha256"]

    # 1. Verify pristine artifact passes
    matching_spec = next(p for p in PackageManager.get_supported_packages() if p.filename == target_pkg["filename"])
    ok, msg = PackageManager.validate_package_integrity(matching_spec, pkg_file)
    assert ok is True, f"Pristine artifact failed validation: {msg}"

    # 2. Mutate 1 byte
    tampered_bytes = bytearray(original_bytes)
    tampered_bytes[0] ^= 0xFF  # Invert first byte
    pkg_file.write_bytes(tampered_bytes)

    # 3. Recalculate SHA-256 and assert mismatch
    tampered_sha = hashlib.sha256(tampered_bytes).hexdigest()
    assert tampered_sha != original_sha

    # 4. Assert release validator rejects tampered artifact
    ok_tampered, fail_msg = PackageManager.validate_package_integrity(matching_spec, pkg_file)
    assert ok_tampered is False
    assert "checksum mismatch" in fail_msg.lower() or "size mismatch" in fail_msg.lower()

    # 5. Restore original bytes
    pkg_file.write_bytes(original_bytes)

    # 6. Assert restored artifact passes validation
    ok_restored, restore_msg = PackageManager.validate_package_integrity(matching_spec, pkg_file)
    assert ok_restored is True, f"Restored artifact failed validation: {restore_msg}"

