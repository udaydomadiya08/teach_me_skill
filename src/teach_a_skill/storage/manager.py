"""Local storage management and category partitioning."""

import json
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.errors import StorageError, StoragePathTraversalError
from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.storage.atomic import atomic_write


class StorageManager(IStorageManager):
    """Manages local storage partitions, atomic operations, and path safety."""

    CATEGORIES = {
        "config",
        "models",
        "recordings",
        "skills",
        "sessions",
        "logs",
        "cache",
        "execution",
        "recovery",
        "learning",
        "perception",
        "memory",
        "audits",
    }

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.expanduser().resolve()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def initialize_directories(self) -> None:
        """Create all canonical storage partitions with strict permissions."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        for cat in self.CATEGORIES:
            cat_dir = self._base_dir / cat
            cat_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, category: str, subpath: Optional[str] = None) -> Path:
        """Resolve a safe, sandboxed path within a storage category.

        Guards against directory traversal attacks.
        """
        if category not in self.CATEGORIES:
            raise StorageError(
                f"Unknown storage category '{category}'. Valid categories: {self.CATEGORIES}"
            )

        cat_root = (self._base_dir / category).resolve()

        if not subpath:
            return cat_root

        # Resolve candidate path
        candidate = (cat_root / subpath).resolve()

        # Sandbox check: candidate must be within cat_root
        try:
            candidate.relative_to(cat_root)
        except ValueError as exc:
            raise StoragePathTraversalError(
                f"Security violation: subpath '{subpath}' attempts to traverse outside '{cat_root}'"
            ) from exc

        return candidate

    def write_atomic_text(self, target_path: Path, content: str) -> None:
        """Atomically write text content."""
        atomic_write(target_path, content, encoding="utf-8")

    def write_atomic_bytes(self, target_path: Path, data: bytes) -> None:
        """Atomically write binary data."""
        atomic_write(target_path, data)

    def read_text(self, target_path: Path) -> str:
        """Read text from storage path."""
        if not target_path.exists():
            raise StorageError(f"Target file does not exist: {target_path}")
        return target_path.read_text(encoding="utf-8")

    def read_bytes(self, target_path: Path) -> bytes:
        """Read binary data from storage path."""
        if not target_path.exists():
            raise StorageError(f"Target file does not exist: {target_path}")
        return target_path.read_bytes()

    def write_metadata(self, target_path: Path, metadata: dict[str, Any]) -> None:
        """Atomically persist structured metadata as JSON."""
        content = json.dumps(metadata, indent=2, sort_keys=True)
        self.write_atomic_text(target_path, content)

    def read_metadata(self, target_path: Path) -> dict[str, Any]:
        """Read structured JSON metadata."""
        raw = self.read_text(target_path)
        try:
            return json.loads(raw)
        except Exception as e:
            raise StorageError(f"Corrupted metadata file '{target_path}': {e}") from e

    def verify_integrity(self) -> dict[str, bool]:
        """Verify storage root and all category partitions are valid and writable."""
        results: dict[str, bool] = {}
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            test_file = self._base_dir / ".integrity_test.tmp"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            results["root"] = True
        except Exception:
            results["root"] = False

        for cat in self.CATEGORIES:
            cat_dir = self._base_dir / cat
            try:
                cat_dir.mkdir(parents=True, exist_ok=True)
                test_file = cat_dir / ".integrity_test.tmp"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
                results[cat] = True
            except Exception:
                results[cat] = False

        return results
