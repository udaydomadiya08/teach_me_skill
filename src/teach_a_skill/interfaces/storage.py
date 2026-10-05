"""Storage subsystem interfaces."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class IStorageManager(ABC):
    """Local storage lifecycle and directory layout interface."""

    @property
    @abstractmethod
    def base_dir(self) -> Path:
        """Root directory for all local-only system data."""
        pass

    @abstractmethod
    def get_path(self, category: str, subpath: Optional[str] = None) -> Path:
        """Resolve a safe, sandboxed path within a storage category."""
        pass

    @abstractmethod
    def write_atomic_text(self, target_path: Path, content: str) -> None:
        """Atomically write text content using a temporary file and atomic rename."""
        pass

    @abstractmethod
    def write_atomic_bytes(self, target_path: Path, data: bytes) -> None:
        """Atomically write binary data using a temporary file and atomic rename."""
        pass

    @abstractmethod
    def read_text(self, target_path: Path) -> str:
        """Read text from storage path."""
        pass

    @abstractmethod
    def read_bytes(self, target_path: Path) -> bytes:
        """Read binary data from storage path."""
        pass

    @abstractmethod
    def verify_integrity(self) -> dict[str, bool]:
        """Verify storage directories exist, are writable, and within bounds."""
        pass
