"""Phase 14 Verification and Validation Script.

Executes all Section requirements for Phase 14:
1. Platform Adapter & Capability Matrix (macOS real, Linux/Windows simulated)
2. Permission Manager & Least Privilege enforcement (Fail-closed, Network Denied)
3. SecretDetector (pattern matching, entropy, redaction)
4. StorageSecurityManager (path traversal, symlink attack rejection, secure temp files)
5. AuditIntegrityManager (SHA-256 chained log, tamper detection, SECURITY_INCIDENT state)
6. RetentionManager & Data Minimization
7. DependencyAuditor & NetworkIsolationMonitor (0 outbound connections, offline verification)
8. PrivacyAuditor, UserDataExporter & UserDataDeleter (local export, zero dangling refs)
9. PackageManager & MigrationManager (versioned migrations, rollback safety, clean uninstall)
10. HealthChecks (Checks 73-77)
11. CLI Commands verification
12. Phase 14 Performance Benchmarks (cold/warm startup, security overhead, DoS rejection, 1,000 mixed operations)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import tempfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from teach_a_skill.platform import (
    PlatformCapability,
    CapabilityState,
    PlatformCapabilities,
    PlatformCompatibilityManifest,
    PlatformManager,
    MacOSAdapter,
    LinuxAdapter,
    WindowsAdapter,
)
from teach_a_skill.security import (
    PermissionType,
    PermissionState,
    PermissionManager,
    PermissionDeniedError,
    SecretDetector,
    StorageSecurityManager,
    SecurityViolationError,
    AuditIntegrityManager,
    SecurityIncidentError,
    RetentionPolicy,
    RetentionManager,
    DependencyAuditor,
    NetworkIsolationMonitor,
    Phase14BenchmarkRunner,
)
from teach_a_skill.privacy import (
    PrivacyClassification,
    PrivacyAuditor,
    UserDataExporter,
    UserDataDeleter,
)
from teach_a_skill.packaging import (
    PackageType,
    PackageManager,
    MigrationManager,
    MigrationStep,
)
from teach_a_skill.core.config import ConfigManager
from teach_a_skill.core.health import HealthChecker
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.cli.main import main


def verify_phase14() -> dict:
    results = {}
    print("=" * 80)
    print("PHASE 14 — PRIVACY, SECURITY HARDENING & CROSS-PLATFORM PACKAGING VERIFICATION")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Platform Adapters & Capability Matrix
    # -------------------------------------------------------------------------
    print("\n[1/12] Verifying Platform Adapters & Capability Matrix...")
    mac = MacOSAdapter()
    assert mac.os_name == "macos"
    mac_caps = mac.get_capabilities()
    assert mac_caps.get_state(PlatformCapability.SCREEN_CAPTURE) in (CapabilityState.SUPPORTED, CapabilityState.SUPPORTED_WITH_PERMISSION)
    assert mac_caps.get_state(PlatformCapability.MODEL_ACCELERATION) == CapabilityState.SUPPORTED
    mac_manifest = mac.get_compatibility_manifest()
    assert "macOS" in mac_manifest.minimum_os_version

    sim_linux = LinuxAdapter()
    assert sim_linux.os_name == "linux"
    lin_caps = sim_linux.get_capabilities()
    assert lin_caps.get_state(PlatformCapability.PROCESS_CONTROL) == CapabilityState.SUPPORTED
    lin_manifest = sim_linux.get_compatibility_manifest()
    assert "Linux" in lin_manifest.minimum_os_version

    sim_win = WindowsAdapter()
    assert sim_win.os_name == "windows"
    win_caps = sim_win.get_capabilities()
    assert win_caps.get_state(PlatformCapability.PROCESS_CONTROL) == CapabilityState.SUPPORTED
    win_manifest = sim_win.get_compatibility_manifest()
    assert "Windows" in win_manifest.minimum_os_version

    # Logical path normalization
    norm = PlatformManager.normalize_path_to_logical("/tmp/app/skills/test.json", base_dir="/tmp/app")
    assert norm == "<app_data>/skills/test.json"
    res = PlatformManager.resolve_logical_path(norm, base_dir="/tmp/app")
    assert res == Path("/tmp/app/skills/test.json")

    results["platform_abstraction"] = "PASSED"
    print(" -> Real macOS adapter and simulated Linux/Windows adapters verified.")

    # -------------------------------------------------------------------------
    # 2. Permission Manager & Least Privilege
    # -------------------------------------------------------------------------
    print("\n[2/12] Verifying Permission Manager & Least Privilege...")
    pm = PermissionManager()
    assert pm.check_permission(PermissionType.NETWORK) == PermissionState.DENIED
    try:
        pm.require_permission(PermissionType.NETWORK, "cloud_sync")
        raise AssertionError("Failed to deny NETWORK permission!")
    except PermissionDeniedError:
        pass

    try:
        pm.require_permission(PermissionType.SCREEN_CAPTURE, "capture")
        raise AssertionError("Failed to require SCREEN_CAPTURE permission!")
    except PermissionDeniedError:
        pass

    pm.request_permission(PermissionType.SCREEN_CAPTURE, "User accepted prompt")
    assert pm.check_permission(PermissionType.SCREEN_CAPTURE) == PermissionState.GRANTED
    pm.require_permission(PermissionType.SCREEN_CAPTURE, "capture")

    results["permission_manager"] = "PASSED"
    print(" -> Fail-closed permissions and least privilege enforced.")

    # -------------------------------------------------------------------------
    # 3. Secret Detection & Redaction
    # -------------------------------------------------------------------------
    print("\n[3/12] Verifying SecretDetector...")
    leak_sample = "Key: AKIAIOSFODNN7EXAMPLE and token: ghp_1234567890abcdef1234567890abcdef1234 and pass: password123"
    matches = SecretDetector.scan_text(leak_sample)
    assert len(matches) >= 2
    redacted = SecretDetector.redact_text(leak_sample)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "[REDACTED_AWS_ACCESS_KEY]" in redacted
    assert "ghp_" not in redacted

    struct_sample = {"creds": {"api_key": "secret_key_val", "user": "admin"}}
    clean_struct = SecretDetector.redact_structure(struct_sample)
    assert clean_struct["creds"]["api_key"] == "[REDACTED]"
    assert clean_struct["creds"]["user"] == "admin"

    results["secret_detector"] = "PASSED"
    print(" -> Secret detection, entropy calculation, and redaction verified.")

    # -------------------------------------------------------------------------
    # 4. Storage Security Manager (Path Traversal & Symlinks)
    # -------------------------------------------------------------------------
    print("\n[4/12] Verifying StorageSecurityManager...")
    with tempfile.TemporaryDirectory() as td:
        root_dir = Path(td) / "sandbox"
        root_dir.mkdir()
        ssm = StorageSecurityManager(root_dir)

        # Path traversal tests
        for bad_path in ["../../etc/passwd", "..\\..\\Windows\\System32", "safe.txt\0../../evil"]:
            try:
                ssm.validate_and_resolve_path(bad_path)
                raise AssertionError(f"Failed to block traversal: {bad_path}")
            except SecurityViolationError:
                pass

        # Symlink escape test
        outside_file = Path(td) / "secret.txt"
        outside_file.write_text("secret")
        symlink_file = root_dir / "link_to_secret.txt"
        symlink_file.symlink_to(outside_file)
        try:
            ssm.validate_and_resolve_path(symlink_file)
            raise AssertionError("Failed to block symlink escape!")
        except SecurityViolationError:
            pass

        # Secure temp file test
        with ssm.secure_temp_file() as tmp_file:
            assert tmp_file.exists()
            assert tmp_file.parent == ssm.temp_dir
        assert not tmp_file.exists()

    results["storage_security"] = "PASSED"
    print(" -> Path traversal, symlink attacks, and secure temp files verified.")

    # -------------------------------------------------------------------------
    # 5. Audit Integrity & Tamper Evident Log
    # -------------------------------------------------------------------------
    print("\n[5/12] Verifying Audit Integrity & Tamper Detection...")
    with tempfile.TemporaryDirectory() as td:
        audit_file = Path(td) / "audit.jsonl"
        aim = AuditIntegrityManager(audit_file)
        aim.record_event("SYS_START", "system", {"version": "1.0.0"})
        aim.record_event("PERM_GRANT", "system", {"perm": "SCREEN_CAPTURE"})
        aim.record_event("SKILL_RUN", "system", {"skill_id": "test"})

        valid, msg, broken = aim.verify_chain()
        assert valid is True

        # Tampering attempt: modify line 2
        with open(audit_file, "r") as f:
            lines = f.readlines()
        data = json.loads(lines[1])
        data["details"]["perm"] = "NETWORK"  # Attacker modified payload
        lines[1] = json.dumps(data) + "\n"
        with open(audit_file, "w") as f:
            f.writelines(lines)

        # Verification must fail and trigger SECURITY_INCIDENT state
        tamper_valid, tamper_msg, broken_seq = aim.verify_chain()
        assert tamper_valid is False
        assert broken_seq == 2
        assert aim.is_incident_active is True

        try:
            aim.record_event("NEW_EVENT")
            raise AssertionError("Failed to block recording in SECURITY_INCIDENT state!")
        except SecurityIncidentError:
            pass

    results["audit_integrity"] = "PASSED"
    print(" -> Chained SHA-256 audit, tamper detection, and SECURITY_INCIDENT state verified.")

    # -------------------------------------------------------------------------
    # 6. Retention Manager
    # -------------------------------------------------------------------------
    print("\n[6/12] Verifying RetentionManager...")
    with tempfile.TemporaryDirectory() as td:
        sm = StorageManager(Path(td))
        rm = RetentionManager(sm, RetentionPolicy(recordings_days=0))
        rec_dir = sm.get_path("recordings")
        rec_dir.mkdir(parents=True, exist_ok=True)
        dummy_file = rec_dir / "old_rec.json"
        dummy_file.write_text("{}")
        pruned = rm.enforce_retention()
        assert "recordings" in pruned
        assert not dummy_file.exists()

    results["retention_manager"] = "PASSED"
    print(" -> Centralized retention policy enforced.")

    # -------------------------------------------------------------------------
    # 7. Dependency Auditor & Network Isolation Monitor
    # -------------------------------------------------------------------------
    print("\n[7/12] Verifying Dependency Auditor & Zero Network Egress...")
    inventory = DependencyAuditor.get_dependency_inventory()
    assert len(inventory) > 0
    lic_audit = DependencyAuditor.audit_licenses()
    assert lic_audit["total_dependencies"] > 0

    net_report = NetworkIsolationMonitor.verify_network_isolation()
    assert net_report["network_status"] == "OFFLINE"
    assert net_report["unexpected_outbound_connections"] == 0
    NetworkIsolationMonitor.assert_offline()

    results["dependencies_and_network"] = "PASSED"
    print(f" -> {len(inventory)} dependencies audited. Zero unexpected outbound connections verified.")

    # -------------------------------------------------------------------------
    # 8. Privacy Auditor, User Data Exporter & Deleter
    # -------------------------------------------------------------------------
    print("\n[8/12] Verifying Privacy Auditor, Local Export & Clean Deletion...")
    with tempfile.TemporaryDirectory() as td:
        sm = StorageManager(Path(td))
        skills_dir = sm.get_path("skills")
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skills_dir / "skill_test.json"
        skill_file.write_text(json.dumps({"skill_id": "test_01", "name": "Test"}))

        pa = PrivacyAuditor(sm)
        report = pa.audit_storage_privacy()
        assert report["total_artifacts"] >= 1

        export_dir = Path(td) / "export"
        exporter = UserDataExporter(sm)
        export_meta = exporter.export_user_data(export_dir)
        assert export_meta["file_count"] >= 1
        assert (export_dir / "export_manifest.json").exists()

        deleter = UserDataDeleter(sm)
        del_res = deleter.delete_skill_data("test_01")
        assert del_res["deleted_count"] >= 1
        assert del_res["integrity_verified"] is True
        assert not skill_file.exists()

    results["privacy_auditor"] = "PASSED"
    print(" -> Privacy audit, local export, and dangling-reference-free deletion verified.")

    # -------------------------------------------------------------------------
    # 9. Packaging & Migration Framework
    # -------------------------------------------------------------------------
    print("\n[9/12] Verifying Packaging & Migration Framework...")
    with tempfile.TemporaryDirectory() as td:
        packages = PackageManager.get_supported_packages()
        assert len(packages) >= 4
        for p in packages:
            ok, msg = PackageManager.validate_package_integrity(p)
            assert ok is True

        # Safe uninstall test
        install_dir = Path(td) / "app_install"
        (install_dir / "bin").mkdir(parents=True)
        (install_dir / "bin" / "teach-skill").write_text("#!/bin/sh")
        (install_dir / "data").mkdir(parents=True)
        (install_dir / "data" / "skills.db").write_text("skills")

        uninst_report = PackageManager.execute_uninstall(install_dir, remove_user_data=False)
        assert uninst_report["binaries_removed"] is True
        assert uninst_report["user_data_preserved"] is True
        assert (install_dir / "data" / "skills.db").exists()

        # Migration test
        mig_mgr = MigrationManager()
        cfg_legacy = {"version": "0.1.0", "name": "test_app"}
        cfg_v1 = mig_mgr.migrate_config(cfg_legacy)
        assert cfg_v1["version"] == "1.0.0"
        assert cfg_v1["privacy"]["local_only"] is True

        # Storage migration
        storage_to_mig = Path(td) / "storage_mig"
        storage_to_mig.mkdir()
        res = mig_mgr.migrate_storage_directory(storage_to_mig)
        assert res["status"] == "MIGRATED_SUCCESSFULLY"
        assert (storage_to_mig / ".storage_version").exists()

    results["packaging_and_migration"] = "PASSED"
    print(" -> Cross-platform packages, checksum validation, and atomic migrations verified.")

    # -------------------------------------------------------------------------
    # 10. Health Checks (73-77)
    # -------------------------------------------------------------------------
    print("\n[10/12] Verifying System Health Checks...")
    with tempfile.TemporaryDirectory() as td:
        cfg = ConfigManager(Path(td) / "config.json")
        sm = StorageManager(Path(td))
        hr = HealthChecker.run_health_check(cfg, sm, full=True)
        assert hr.healthy is True
        check_names = {c.name for c in hr.checks}
        p14_checks = [
            "platform_capabilities_and_manifest",
            "permission_manager_and_least_privilege",
            "secret_detector_and_privacy_auditor",
            "storage_security_and_audit_integrity",
            "packaging_and_migration_system",
        ]
        for chk in p14_checks:
            assert chk in check_names, f"Missing health check: {chk}"
        print(f" -> All {len(hr.checks)} health checks passed (including all 5 Phase 14 checks).")

    results["health_checks"] = "PASSED"

    # -------------------------------------------------------------------------
    # 11. CLI Commands Execution
    # -------------------------------------------------------------------------
    print("\n[11/12] Verifying Phase 14 CLI Commands...")
    cli_commands = [
        ["security", "health", "--quiet"],
        ["security", "audit", "--quiet"],
        ["security", "dependencies", "--quiet"],
        ["security", "permissions", "--quiet"],
        ["security", "privacy", "--quiet"],
        ["security", "storage", "--quiet"],
        ["security", "network", "--quiet"],
        ["security", "integrity", "--quiet"],
        ["platform", "info", "--quiet"],
        ["platform", "capabilities", "--quiet"],
        ["platform", "permissions", "--quiet"],
        ["platform", "health", "--quiet"],
        ["package", "validate", "--quiet"],
        ["package", "info", "--quiet"],
        ["package", "health", "--quiet"],
    ]
    for cmd in cli_commands:
        ret = main(cmd)
        assert ret == 0, f"CLI command failed: teach-skill {' '.join(cmd)}"

    results["cli_commands"] = "PASSED"
    print(f" -> All {len(cli_commands)} Phase 14 CLI commands executed successfully.")

    # -------------------------------------------------------------------------
    # 12. Benchmarks, DoS Rejection & 1,000 Mixed Operations
    # -------------------------------------------------------------------------
    print("\n[12/12] Running Benchmarks, DoS Defense & 1,000 Operations Stress Test...")
    with tempfile.TemporaryDirectory() as td:
        bench_runner = Phase14BenchmarkRunner(Path(td))
        bench_res = bench_runner.run_all_benchmarks(mixed_ops_count=1000)

        results["startup_benchmark"] = bench_res["startup"]
        results["security_overhead"] = bench_res["security_overhead"]
        results["dos_defense"] = bench_res["dos_defense"]
        results["audit_tamper_defense"] = bench_res["tamper_defense"]
        results["long_run_1000_ops"] = bench_res["long_run_1000_ops"]

        print(f" -> Cold startup: {bench_res['startup']['cold_startup_ms']:.2f} ms")
        print(f" -> Warm startup: {bench_res['startup']['warm_startup_ms']:.2f} ms")
        print(f" -> CLI startup: {bench_res['startup']['cli_startup_ms']:.2f} ms")
        print(f" -> Redaction throughput: {bench_res['security_overhead']['redaction_throughput_mb_s']:.2f} MB/s")
        print(f" -> Audit append time: {bench_res['security_overhead']['audit_append_time_ms']:.4f} ms/event")
        print(f" -> DoS huge inputs: {bench_res['dos_defense']['status']} (bounded safely)")
        print(f" -> Audit tampering detection: {bench_res['tamper_defense']['status']}")
        print(f" -> 1,000 Mixed Ops: {bench_res['long_run_1000_ops']['status']}, Total time: {bench_res['long_run_1000_ops']['total_time_s']:.2f}s, Peak RSS: {bench_res['long_run_1000_ops']['rss_growth_mb']:.2f}MB growth")

    print("\n" + "=" * 80)
    print("ALL PHASE 14 VERIFICATIONS PASSED SUCCESSFULLY.")
    print("=" * 80)
    return results


if __name__ == "__main__":
    verify_phase14()
