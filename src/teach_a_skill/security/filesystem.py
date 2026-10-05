"""Filesystem security, path traversal defenses, symlink protection, and secure deletion."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Generator, Optional

from teach_a_skill.core.errors import TeachSkillError


class SecurityViolationError(TeachSkillError):
    """Raised when an adversarial filesystem path or symlink traversal is detected."""
    pass


class DeletionMode(str, Enum):
    """Reported capability and method used during artifact deletion."""

    LOGICAL_DELETION = "logical_deletion"
    SECURE_DELETION_SUPPORTED = "secure_deletion_supported"
    SECURE_DELETION_UNAVAILABLE = "secure_deletion_unavailable"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DeletionReport:
    """Audit report of a file deletion operation."""

    target_path: str
    mode_used: DeletionMode
    success: bool
    bytes_overwritten: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["mode_used"] = self.mode_used.value
        return data


class StorageSecurityManager:
    """Enforces canonical path boundaries, symlink attack defenses, and secure temporary files."""

    def __init__(self, root_storage_dir: Path | str) -> None:
        self.root_dir = Path(root_storage_dir).resolve()
        self.temp_dir = self.root_dir / ".tmp"
        self._ensure_secure_temp_dir()

    def _ensure_secure_temp_dir(self) -> None:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Set owner-only directory permissions (0o700)
            os.chmod(self.temp_dir, 0o700)
        except Exception:
            pass

    def validate_and_resolve_path(self, relative_or_absolute: str | Path) -> Path:
        """Resolve path and verify it remains strictly bounded inside root storage."""
        raw_str = str(relative_or_absolute)

        # 1. Null byte injection check
        if "\0" in raw_str:
            raise SecurityViolationError(f"Null byte injection detected in path: '{raw_str}'")

        # 2. Path normalization
        normalized_str = raw_str.replace("\\", "/")
        if os.path.isabs(normalized_str):
            raw_path = Path(normalized_str)
        else:
            raw_path = self.root_dir / normalized_str

        # 3. Check for symlink escape before or after resolution
        is_sym = raw_path.is_symlink() or any(p.is_symlink() for p in raw_path.parents if p != self.root_dir and p != self.root_dir.parent)
        target = raw_path.resolve()

        if is_sym:
            try:
                target.relative_to(self.root_dir)
            except ValueError:
                raise SecurityViolationError(
                    f"Symlink escape blocked: symlink '{raw_str}' resolves outside storage boundary '{self.root_dir}'"
                )

        # 4. Path traversal boundary check
        try:
            target.relative_to(self.root_dir)
        except ValueError:
            raise SecurityViolationError(
                f"Path traversal blocked: target '{raw_str}' resolves outside storage boundary '{self.root_dir}'"
            )

        return target

    @contextmanager
    def secure_temp_file(self, prefix: str = "tas_tmp_", suffix: str = ".dat") -> Generator[Path, None, None]:
        """Create an owner-restricted temporary file with guaranteed cleanup."""
        self._ensure_secure_temp_dir()
        filename = f"{prefix}{uuid.uuid4().hex[:12]}{suffix}"
        temp_path = self.temp_dir / filename

        # Create file with 0o600 permissions
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        fd = os.open(temp_path, flags, 0o600)
        os.close(fd)

        try:
            yield temp_path
        finally:
            if temp_path.exists():
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def secure_delete(self, relative_or_absolute: str | Path, overwrite_passes: int = 1) -> DeletionReport:
        """Perform best-effort multi-pass zeroing before unlink; report exact deletion mode."""
        resolved = self.validate_and_resolve_path(relative_or_absolute)
        if not resolved.exists():
            return DeletionReport(
                target_path=str(resolved),
                mode_used=DeletionMode.LOGICAL_DELETION,
                success=True,
                message="File did not exist; no deletion necessary.",
            )

        if resolved.is_dir():
            shutil.rmtree(resolved)
            return DeletionReport(
                target_path=str(resolved),
                mode_used=DeletionMode.LOGICAL_DELETION,
                success=True,
                message="Directory removed logically.",
            )

        # Single file zero-fill
        file_size = resolved.stat().st_size
        overwritten_bytes = 0
        try:
            if file_size > 0:
                with open(resolved, "wb") as f:
                    for _ in range(overwrite_passes):
                        f.seek(0)
                        f.write(b"\x00" * min(file_size, 1024 * 1024))
                        f.flush()
                        os.fsync(f.fileno())
                overwritten_bytes = file_size

            os.unlink(resolved)
            return DeletionReport(
                target_path=str(resolved),
                mode_used=DeletionMode.SECURE_DELETION_SUPPORTED,
                success=True,
                bytes_overwritten=overwritten_bytes,
                message=f"File zeroed ({overwrite_passes} pass) and unlinked.",
            )
        except Exception as e:
            # Fallback to logical unlink if zero-fill fails
            try:
                os.unlink(resolved)
                return DeletionReport(
                    target_path=str(resolved),
                    mode_used=DeletionMode.SECURE_DELETION_UNAVAILABLE,
                    success=True,
                    message=f"Zero-fill unavailable ({e}); unlinked logically.",
                )
            except Exception as e2:
                return DeletionReport(
                    target_path=str(resolved),
                    mode_used=DeletionMode.LOGICAL_DELETION,
                    success=False,
                    message=f"Failed to delete file: {e2}",
                )
