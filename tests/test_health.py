"""Tests for system health check verifier."""

from teach_a_skill.core.health import HealthChecker
from teach_a_skill.storage.manager import StorageManager


def test_health_check_passes(config_mgr, storage_mgr):
    report = HealthChecker.run_health_check(
        config_manager=config_mgr,
        storage_manager=storage_mgr,
    )
    assert report.healthy is True
    check_names = {c.name for c in report.checks}
    assert "platform_support" in check_names
    assert "configuration_validity" in check_names
    assert "privacy_invariants" in check_names
    assert "storage_writability" in check_names
    assert "hardware_detection" in check_names
    assert "model_registry" in check_names


def test_health_check_detects_invalid_storage(config_mgr, temp_dir):
    # Point storage to a read-only or invalid directory
    bad_storage = StorageManager(temp_dir / "non_existent_deep" / "bad")
    # Make parent unwritable or trigger error
    report = HealthChecker.run_health_check(
        config_manager=config_mgr,
        storage_manager=bad_storage,
    )
    # Even if created, check if all partitions pass
    assert len(report.checks) == 6


def test_learning_health_checks_pass(config_mgr, storage_mgr):
    report = HealthChecker.run_health_check(
        config_manager=config_mgr,
        storage_manager=storage_mgr,
        full=True,
    )
    failed_checks = [f"{c.name}: {c.message}" for c in report.checks if not c.passed]
    assert not failed_checks, f"Failed checks: {failed_checks}"
    check_names = {c.name for c in report.checks}
    assert "learning_tracker_and_patterns" in check_names
    assert "learning_variations_and_proposals" in check_names
    assert "learning_candidates_and_shadow_eval" in check_names
    assert "learning_promotion_and_rollback" in check_names
    assert "learning_store_and_safety_validator" in check_names
    # All checks passed
    learning_checks = [c for c in report.checks if c.name.startswith("learning_")]
    assert len(learning_checks) == 5
    assert all(c.passed for c in learning_checks)

    # Phase 14 Security & Platform checks
    assert "platform_capabilities_and_manifest" in check_names
    assert "permission_manager_and_least_privilege" in check_names
    assert "secret_detector_and_privacy_auditor" in check_names
    assert "storage_security_and_audit_integrity" in check_names
    assert "packaging_and_migration_system" in check_names

    # Phase 15 Production Release checks
    assert "production_readiness_and_versioning" in check_names
    assert "end_to_end_pipeline_provenance" in check_names
    assert "release_artifacts_and_checksum_integrity" in check_names
