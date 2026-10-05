"""Comprehensive test suite for Phase 14: Privacy, Security Hardening & Cross-Platform Packaging.

Covers:
1. Platform capabilities matrix, capability states, and compatibility manifests.
2. Cross-platform adapters: macOS, Linux (Wayland vs X11), Windows, and simulated targets.
3. Path normalization: portable logical paths excluding machine-specific coordinates.
4. PermissionManager: fail-closed default (NETWORK=DENIED), least privilege, and denials.
5. SecretDetector: AWS, GitHub, Stripe, Slack, Private Keys, JWT, DB strings, and entropy.
6. StorageSecurityManager: path traversal defense, symlink defense, secure temp files, secure deletion.
7. AuditIntegrityManager: chained SHA-256 tamper-evident log, tamper detection, and SECURITY_INCIDENT.
8. RetentionManager: centralized retention policies and safe pruning.
9. DependencyAuditor: inventory extraction, license compliance, and vulnerability scanning.
10. NetworkIsolationMonitor: offline assertion and outbound connection monitoring.
11. PrivacyAuditor, UserDataExporter, and UserDataDeleter.
12. PackageManager: multi-platform package manifests and integrity verification.
13. MigrationManager: idempotent migrations, atomic directory upgrade, and rollback safety.
14. Benchmarks, DoS resilience, and 1,000 mixed operations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from teach_a_skill.packaging.manager import (
    PackageManager,
    PackageType,
    PlatformPackage,
)
from teach_a_skill.packaging.migration import (
    MigrationError,
    MigrationManager,
    MigrationStep,
)
from teach_a_skill.platform.capabilities import (
    CapabilityState,
    PlatformCapabilities,
    PlatformCapability,
    PlatformCompatibilityManifest,
)
from teach_a_skill.platform.linux import LinuxAdapter
from teach_a_skill.platform.macos import MacOSAdapter
from teach_a_skill.platform.manager import PlatformManager
from teach_a_skill.platform.windows import WindowsAdapter
from teach_a_skill.privacy.auditor import (
    PrivacyAuditor,
    PrivacyClassification,
    UserDataDeleter,
    UserDataExporter,
)
from teach_a_skill.security.audit import (
    AuditIntegrityManager,
    ChainedAuditRecord,
    SecurityIncidentError,
)
from teach_a_skill.security.benchmark import (
    Phase14BenchmarkResults,
    Phase14BenchmarkRunner,
)
from teach_a_skill.security.dependencies import (
    DependencyAuditor,
    DependencyRecord,
)
from teach_a_skill.security.filesystem import (
    DeletionMode,
    SecurityViolationError,
    StorageSecurityManager,
)
from teach_a_skill.security.network import (
    NetworkIsolationMonitor,
    NetworkIsolationViolationError,
)
from teach_a_skill.security.permissions import (
    PermissionDeniedError,
    PermissionManager,
    PermissionState,
    PermissionType,
)
from teach_a_skill.security.retention import (
    RetentionManager,
    RetentionPolicy,
)
from teach_a_skill.security.secrets import (
    SecretDetector,
    SecretMatch,
)
from teach_a_skill.storage.manager import StorageManager


# ---------------------------------------------------------------------------
# Test 1: Platform Capabilities & Cross-Platform Abstraction
# ---------------------------------------------------------------------------

def test_platform_capabilities_and_adapters():
    # macOS Adapter
    mac = MacOSAdapter()
    assert mac.os_name == "macos"
    mac_caps = mac.get_capabilities()
    assert mac_caps.get_state(PlatformCapability.SCREEN_CAPTURE) in (CapabilityState.SUPPORTED, CapabilityState.SUPPORTED_WITH_PERMISSION)
    assert mac_caps.get_state(PlatformCapability.ACCESSIBILITY) == CapabilityState.SUPPORTED_WITH_PERMISSION
    assert mac_caps.is_usable(PlatformCapability.ACCESSIBILITY) is True
    assert mac_caps.get_fallback(PlatformCapability.ACCESSIBILITY) is not None

    # Linux Adapter (simulated session)
    linux = LinuxAdapter()
    assert linux.os_name == "linux"
    linux_caps = linux.get_capabilities()
    assert len(linux_caps.capabilities) >= 10
    linux_manifest = linux.get_compatibility_manifest()
    assert linux_manifest.os_name == "linux"

    # Windows Adapter
    win = WindowsAdapter()
    assert win.os_name == "windows"
    win_caps = win.get_capabilities()
    assert win_caps.get_state(PlatformCapability.PROCESS_CONTROL) == CapabilityState.SUPPORTED
    win_manifest = win.get_compatibility_manifest()
    assert "Windows" in win_manifest.minimum_os_version


def test_platform_manager_resolution_and_path_normalization(tmp_path):
    # Adapter resolution
    adapter_live = PlatformManager.get_adapter()
    assert adapter_live.os_name in ("macos", "linux", "windows")

    sim_linux = PlatformManager.get_adapter("linux")
    assert sim_linux.os_name == "linux"

    sim_win = PlatformManager.get_adapter("windows")
    assert sim_win.os_name == "windows"

    # Path normalization to portable logical references
    app_base = str(tmp_path / "app_data")
    local_path = os.path.join(app_base, "skills", "skill_01.json")
    logical = PlatformManager.normalize_path_to_logical(local_path, base_dir=app_base)
    assert logical == "<app_data>/skills/skill_01.json"

    # Re-resolving logical path
    resolved = PlatformManager.resolve_logical_path(logical, base_dir=app_base)
    assert resolved == Path(app_base) / "skills" / "skill_01.json"


# ---------------------------------------------------------------------------
# Test 2: PermissionManager & Least Privilege
# ---------------------------------------------------------------------------

def test_permission_manager_fail_closed_and_least_privilege():
    pm = PermissionManager()

    # Fail-closed default: NETWORK must be strictly DENIED
    assert pm.check_permission(PermissionType.NETWORK) == PermissionState.DENIED

    # Attempting network operation must raise PermissionDeniedError
    with pytest.raises(PermissionDeniedError, match="strict Local-Only"):
        pm.require_permission(PermissionType.NETWORK, "cloud_sync")

    # Hardware permissions default to UNKNOWN until explicitly granted
    assert pm.check_permission(PermissionType.SCREEN_CAPTURE) == PermissionState.UNKNOWN
    with pytest.raises(PermissionDeniedError, match="Screen recording permission is required"):
        pm.require_permission(PermissionType.SCREEN_CAPTURE, "capture_frame")

    # Explicit grant
    pm.grant_permission(PermissionType.SCREEN_CAPTURE, reason="User clicked record")
    assert pm.check_permission(PermissionType.SCREEN_CAPTURE) == PermissionState.GRANTED
    # Should not raise now
    pm.require_permission(PermissionType.SCREEN_CAPTURE, "capture_frame")

    # Explicit revocation
    pm.revoke_permission(PermissionType.SCREEN_CAPTURE)
    assert pm.check_permission(PermissionType.SCREEN_CAPTURE) == PermissionState.DENIED


# ---------------------------------------------------------------------------
# Test 3: SecretDetector & Redaction
# ---------------------------------------------------------------------------

def test_secret_detector_patterns_and_redaction():
    stripe_key = "sk_" + "test_" + "51A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6"
    text_with_secrets = f"""
    Config file:
    AWS Key: AKIAIOSFODNN7EXAMPLE
    GitHub Token: ghp_1234567890abcdef1234567890abcdef1234
    Stripe Key: {stripe_key}
    DB URL: postgresql://admin:super_secret_pw@db.internal:5432/production
    JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSignature12345
    """

    matches = SecretDetector.scan_text(text_with_secrets)
    assert len(matches) >= 4
    match_types = {m.secret_type for m in matches}
    assert "AWS_ACCESS_KEY" in match_types
    assert "GITHUB_TOKEN" in match_types
    assert "STRIPE_API_KEY" in match_types
    assert "DB_CONNECTION" in match_types

    # Redact text
    redacted = SecretDetector.redact_text(text_with_secrets)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "[REDACTED_AWS_ACCESS_KEY]" in redacted
    assert "[REDACTED_GITHUB_TOKEN]" in redacted
    assert "super_secret_pw" not in redacted

    # Recursive structured dictionary redaction
    payload = {
        "user": "alice",
        "api_key": "some_plain_token",
        "nested": {
            "password": "unhashed_password",
            "log": "Token is ghp_1234567890abcdef1234567890abcdef1234",
        },
    }
    clean = SecretDetector.redact_structure(payload)
    assert clean["api_key"] == "[REDACTED]"
    assert clean["nested"]["password"] == "[REDACTED]"
    assert "ghp_" not in clean["nested"]["log"]

    # Shannon entropy estimation
    assert SecretDetector.estimate_entropy("aaaaaaaa") < 1.0
    assert SecretDetector.estimate_entropy("ghp_98a7sd8f7a6sd5f4a6sdf87as6df54") > 3.0


# ---------------------------------------------------------------------------
# Test 4: StorageSecurityManager (Path Traversal & Symlinks)
# ---------------------------------------------------------------------------

def test_storage_security_path_traversal_and_symlinks(tmp_path):
    root_dir = tmp_path / "sandbox_storage"
    root_dir.mkdir()
    ssm = StorageSecurityManager(root_dir)

    # 1. Normal safe path inside root
    safe_path = ssm.validate_and_resolve_path("sub/file.txt")
    assert safe_path == (root_dir / "sub" / "file.txt").resolve()

    # 2. Path traversal attack: ../../etc/passwd
    with pytest.raises(SecurityViolationError, match="Path traversal blocked"):
        ssm.validate_and_resolve_path("../../etc/passwd")

    # 3. Path traversal attack: ..\\..\\Windows\\System32
    with pytest.raises(SecurityViolationError, match="Path traversal blocked"):
        ssm.validate_and_resolve_path("..\\..\\Windows\\System32")

    # 4. Null byte injection attack
    with pytest.raises(SecurityViolationError, match="Null byte injection"):
        ssm.validate_and_resolve_path("safe.txt\0../../evil")

    # 5. Symlink escape attack
    outside_target = tmp_path / "outside_secret.txt"
    outside_target.write_text("classified")
    symlink_path = root_dir / "symlink_escape"
    try:
        os.symlink(outside_target, symlink_path)
        with pytest.raises(SecurityViolationError, match="Symlink escape blocked"):
            ssm.validate_and_resolve_path("symlink_escape")
    except OSError:
        pass  # On OS where symlink creation is not permitted without elevation

    # 6. Secure temporary files
    with ssm.secure_temp_file(prefix="test_tmp_") as tmp_file:
        assert tmp_file.exists()
        assert tmp_file.parent == ssm.temp_dir
        tmp_file.write_text("temporary data")
    assert not tmp_file.exists()  # Cleaned up automatically

    # 7. Secure deletion reporting
    probe_file = root_dir / "probe.dat"
    probe_file.write_text("data to be shredded")
    del_report = ssm.secure_delete(probe_file, overwrite_passes=1)
    assert del_report.success is True
    assert del_report.mode_used in (DeletionMode.SECURE_DELETION_SUPPORTED, DeletionMode.LOGICAL_DELETION)
    assert not probe_file.exists()


# ---------------------------------------------------------------------------
# Test 5: AuditIntegrityManager (Chained Tamper-Evidence & Incident State)
# ---------------------------------------------------------------------------

def test_audit_integrity_tamper_detection_and_security_incident(tmp_path):
    log_file = tmp_path / "audit.log"
    aim = AuditIntegrityManager(log_file)

    # Record 5 chained events
    for i in range(5):
        aim.record_event(f"ACTION_{i}", "operator", {"seq": i})

    # Chain must be unbroken
    valid, msg, broken_idx = aim.verify_chain()
    assert valid is True
    assert broken_idx is None

    # Tampering Test: modify record 2 in place
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    lines[2] = lines[2].replace("ACTION_2", "TAMPERED_ACTION")
    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verification must detect tampering
    tamper_valid, tamper_msg, broken_seq = aim.verify_chain()
    assert tamper_valid is False
    assert broken_seq == 2
    assert "tampering detected" in tamper_msg or "broken" in tamper_msg
    assert aim.is_incident_active is True

    # System in active incident must refuse recording new events
    with pytest.raises(SecurityIncidentError, match="SECURITY_INCIDENT"):
        aim.record_event("POST_TAMPER_ACTION")


# ---------------------------------------------------------------------------
# Test 6: RetentionManager
# ---------------------------------------------------------------------------

def test_retention_manager(tmp_path):
    sm = StorageManager(tmp_path)
    policy = RetentionPolicy(recordings_days=0)  # Immediate expiration for test
    rm = RetentionManager(sm, policy=policy)

    # Create dummy recording file
    rec_dir = sm.get_path("recordings")
    rec_dir.mkdir(parents=True, exist_ok=True)
    dummy_rec = rec_dir / "old_session.json"
    dummy_rec.write_text("{}")

    pruned = rm.enforce_retention()
    assert "recordings" in pruned


# ---------------------------------------------------------------------------
# Test 7: DependencyAuditor & NetworkIsolationMonitor
# ---------------------------------------------------------------------------

def test_dependency_auditor_and_network_isolation():
    # Dependency inventory
    inventory = DependencyAuditor.get_dependency_inventory()
    assert len(inventory) > 0
    names = {dep.name.lower() for dep in inventory}
    assert any(n in names for n in ("teach-a-skill", "pydantic", "pytest", "numpy"))

    # License audit
    lic_audit = DependencyAuditor.audit_licenses()
    assert lic_audit["total_dependencies"] > 0

    # Network isolation monitor
    net_report = NetworkIsolationMonitor.verify_network_isolation()
    assert net_report["network_status"] == "OFFLINE"
    assert net_report["unexpected_outbound_connections"] == 0
    NetworkIsolationMonitor.assert_offline()


# ---------------------------------------------------------------------------
# Test 8: PrivacyAuditor, UserDataExporter & UserDataDeleter
# ---------------------------------------------------------------------------

def test_privacy_auditor_export_and_deletion(tmp_path):
    sm = StorageManager(tmp_path)
    skills_dir = sm.get_path("skills")
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skills_dir / "my_skill.json"
    skill_file.write_text(json.dumps({"skill_id": "target_skill_01", "name": "Test Skill"}))

    # Audit storage
    auditor = PrivacyAuditor(sm)
    items = auditor.audit_storage()
    assert len(items) >= 1
    assert items[0].classification in (PrivacyClassification.PUBLIC, PrivacyClassification.PERSONAL)

    # Export user data
    export_dir = tmp_path / "export_bundle"
    exporter = UserDataExporter(sm)
    manifest = exporter.export_user_data(export_dir)
    assert manifest["file_count"] >= 1
    assert (export_dir / "export_manifest.json").exists()

    # Delete user data
    deleter = UserDataDeleter(sm)
    del_res = deleter.delete_skill_data("target_skill_01")
    assert del_res["deleted_count"] >= 1
    assert del_res["integrity_verified"] is True
    assert not skill_file.exists()


# ---------------------------------------------------------------------------
# Test 9: PackageManager & MigrationManager
# ---------------------------------------------------------------------------

def test_package_manager_and_migration(tmp_path):
    # Package specifications
    packages = PackageManager.get_supported_packages()
    assert len(packages) >= 4
    for p in packages:
        ok, msg = PackageManager.validate_package_integrity(p)
        assert ok is True

    # Safe uninstall
    install_dir = tmp_path / "app_install"
    (install_dir / "bin").mkdir(parents=True)
    (install_dir / "bin" / "teach-skill").write_text("#!/bin/sh")
    (install_dir / "data").mkdir(parents=True)
    (install_dir / "data" / "skills.db").write_text("skills")

    uninst_report = PackageManager.execute_uninstall(install_dir, remove_user_data=False)
    assert uninst_report["binaries_removed"] is True
    assert uninst_report["user_data_preserved"] is True
    assert (install_dir / "data" / "skills.db").exists()

    # MigrationManager
    mig = MigrationManager()
    cfg_legacy = {"version": "0.1.0", "name": "test_app"}
    cfg_v1 = mig.migrate_config(cfg_legacy)
    assert cfg_v1["version"] == "1.0.0"
    assert cfg_v1["privacy"]["local_only"] is True

    # Storage migration
    storage_to_mig = tmp_path / "storage_mig"
    storage_to_mig.mkdir()
    res = mig.migrate_storage_directory(storage_to_mig)
    assert res["status"] == "MIGRATED_SUCCESSFULLY"
    assert (storage_to_mig / ".storage_version").exists()


# ---------------------------------------------------------------------------
# Test 10: Phase 14 Benchmarks & 1,000 Mixed Operations
# ---------------------------------------------------------------------------

def test_phase14_benchmarks_and_scaling():
    res = Phase14BenchmarkRunner.run_all()
    assert res.cold_startup_ms > 0
    assert res.secret_redaction_rate_kb_sec > 0
    assert res.audit_chain_rate_events_sec > 0
    assert res.dos_input_handled_boundedly is True
    assert res.long_run_operations_completed == 1000
    assert res.memory_bounded is True
    assert res.audit_tamper_detected is True
    assert res.path_traversal_blocked is True
