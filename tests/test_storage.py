"""Tests for storage subsystem and atomic operations."""

import pytest

from teach_a_skill.core.errors import (
    StorageError,
    StoragePathTraversalError,
)
from teach_a_skill.storage.manager import StorageManager


def test_directory_initialization(storage_mgr):
    for cat in StorageManager.CATEGORIES:
        cat_dir = storage_mgr.base_dir / cat
        assert cat_dir.exists()
        assert cat_dir.is_dir()


def test_safe_path_resolution(storage_mgr):
    p = storage_mgr.get_path("skills", "my_skill.json")
    expected = (storage_mgr.base_dir / "skills" / "my_skill.json").resolve()
    assert p == expected


def test_path_traversal_attack_blocked(storage_mgr):
    with pytest.raises(StoragePathTraversalError, match="Security violation"):
        storage_mgr.get_path("skills", "../../../etc/passwd")


def test_atomic_write_text(storage_mgr):
    target = storage_mgr.get_path("skills", "test.txt")
    storage_mgr.write_atomic_text(target, "hello local skill")
    assert target.exists()
    assert storage_mgr.read_text(target) == "hello local skill"


def test_atomic_write_bytes(storage_mgr):
    target = storage_mgr.get_path("cache", "test.bin")
    data = b"\x00\x01\x02\x03\xff"
    storage_mgr.write_atomic_bytes(target, data)
    assert target.exists()
    assert storage_mgr.read_bytes(target) == data


def test_metadata_write_and_read(storage_mgr):
    meta_path = storage_mgr.get_path("sessions", "session_meta.json")
    meta_data = {"session_id": "sess_123", "steps": 5, "completed": True}
    storage_mgr.write_metadata(meta_path, meta_data)

    loaded = storage_mgr.read_metadata(meta_path)
    assert loaded == meta_data


def test_read_nonexistent_file_raises_storage_error(storage_mgr):
    target = storage_mgr.get_path("recordings", "missing.raw")
    with pytest.raises(StorageError, match="Target file does not exist"):
        storage_mgr.read_text(target)


def test_integrity_verification(storage_mgr):
    integrity = storage_mgr.verify_integrity()
    assert integrity["root"] is True
    for cat in StorageManager.CATEGORIES:
        assert integrity[cat] is True
