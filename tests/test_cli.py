"""Tests for CLI interface."""

import pytest

from teach_a_skill.cli.main import main


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "teach-skill" in captured.out


def test_cli_status(capsys):
    ret = main(["status", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Teach A Skill - Phase 1 Foundation Status" in captured.out


def test_cli_hardware(capsys):
    ret = main(["hardware", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Hardware Capability Profile" in captured.out


def test_cli_budget(capsys):
    ret = main(["budget", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Adaptive Resource Allocation Budget" in captured.out


def test_cli_health(capsys):
    ret = main(["health", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Overall Status: HEALTHY" in captured.out


def test_cli_benchmark(capsys):
    ret = main(["benchmark", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Baseline Performance Benchmark" in captured.out


def test_cli_registry(capsys):
    ret = main(["registry", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Model Registry" in captured.out


def test_cli_json_status(capsys):
    ret = main(["status", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    assert '"version": "0.2.0"' in captured.out


def test_cli_memory(capsys):
    ret = main(["memory", "models", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Phase 9 Skill Memory" in captured.out


def test_cli_execution_health(capsys):
    ret = main(["execution", "health", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Phase 10 Execution & Semantic Grounding Health" in captured.out
    assert "HEALTHY" in captured.out


def test_cli_execution_observe(capsys):
    ret = main(["execution", "observe", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Environment Observation Snapshot" in captured.out


def test_cli_execution_benchmark(capsys):
    ret = main(["execution", "benchmark", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Phase 10 Execution & Semantic Grounding Benchmarks" in captured.out


def test_cli_execution_validate(capsys):
    ret = main(["execution", "validate", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Execution Validation Report" in captured.out
    assert "VALID" in captured.out


def test_cli_execution_list(capsys):
    ret = main(["execution", "list", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Execution Sessions" in captured.out


def test_cli_learning_status(capsys):
    ret = main(["learning", "status", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Learning & Skill Improvement Status" in captured.out


def test_cli_learning_health(capsys):
    ret = main(["learning", "health", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Overall Status: HEALTHY" in captured.out


def test_cli_learning_validate(capsys):
    ret = main(["learning", "validate", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Phase 13 Learning Safety & Boundary Validation" in captured.out
    assert "Candidate Integrity & Non-Tampering" in captured.out


def test_cli_learning_benchmark(capsys):
    ret = main(["learning", "benchmark", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Phase 13 Learning Subsystem Benchmarks" in captured.out


def test_cli_learning_compare(capsys):
    ret = main(["learning", "compare", "1.0.0", "1.0.1", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Version Comparison: 1.0.0 vs 1.0.1" in captured.out


def test_cli_learning_rollback(capsys):
    ret = main(["learning", "rollback", "test_skill", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Skill Rollback Executed: test_skill" in captured.out


def test_cli_learning_experiments(capsys):
    ret = main(["learning", "experiments", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Active Learning Experiments" in captured.out


def test_cli_security_commands(capsys):
    # security health
    ret = main(["security", "health", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Security Subsystem Health" in captured.out or "Security & Hardening Health" in captured.out)

    # security audit
    ret = main(["security", "audit", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Security & Audit Integrity Report" in captured.out or "Cryptographic Audit Log Integrity" in captured.out)

    # security dependencies
    ret = main(["security", "dependencies", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Dependency Supply-Chain Audit" in captured.out or "Supply-Chain & Dependency Audit" in captured.out)

    # security permissions
    ret = main(["security", "permissions", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Canonical Permissions State" in captured.out or "Least-Privilege Permission Grants" in captured.out)

    # security privacy
    ret = main(["security", "privacy", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Privacy Classification & Retention Audit" in captured.out or "Privacy Audit" in captured.out)

    # security storage
    ret = main(["security", "storage", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Filesystem & Storage Boundary Security" in captured.out or "Storage & Filesystem Security" in captured.out)

    # security network
    ret = main(["security", "network", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Network Isolation & Zero-Egress Status" in captured.out or "Network Isolation & Telemetry Defense" in captured.out)

    # security integrity
    ret = main(["security", "integrity", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Cryptographic Audit Trail Integrity" in captured.out or "System & Artifact Integrity Report" in captured.out)


def test_cli_platform_commands(capsys):
    # platform info
    ret = main(["platform", "info", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Platform Architecture Information" in captured.out or "Host Platform Specification" in captured.out)

    # platform capabilities
    ret = main(["platform", "capabilities", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Platform Capability Matrix" in captured.out

    # platform permissions
    ret = main(["platform", "permissions", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Platform Permissions Audit" in captured.out or "OS & Subsystem Permissions" in captured.out)

    # platform health
    ret = main(["platform", "health", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Platform Adapter Health & Compatibility" in captured.out or "Platform Health" in captured.out)


def test_cli_package_commands(capsys):
    # package validate
    ret = main(["package", "validate", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Packaging System Validation" in captured.out or "Platform Package Integrity Validation" in captured.out)

    # package info
    ret = main(["package", "info", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Package Target Architecture & Metadata" in captured.out or "Platform Packages & Distribution Artifacts" in captured.out)

    # package health
    ret = main(["package", "health", "--quiet"])
    assert ret == 0
    captured = capsys.readouterr()
    assert ("Packaging & Migration Health Status" in captured.out or "Health" in captured.out)



