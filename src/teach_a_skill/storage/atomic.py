"""Atomic file operations with data integrity guarantees."""

import os
import tempfile
from pathlib import Path
from typing import Union

from teach_a_skill.core.errors import StorageError


def atomic_write(target_path: Path, data: Union[str, bytes], encoding: str = "utf-8") -> None:
    """Atomically write data to target path.

    Writes to a temporary file in the same directory, flushes, fsyncs,
    and replaces the target file atomically.
    """
    target_path = target_path.resolve()
    parent_dir = target_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Use same directory so rename/replace is guaranteed atomic (same filesystem)
    fd, temp_file_path = tempfile.mkstemp(
        dir=parent_dir,
        prefix=f".{target_path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_file_path)

    try:
        with open(
            fd,
            "wb" if isinstance(data, (bytes, bytearray)) else "w",
            encoding=None if isinstance(data, (bytes, bytearray)) else encoding,
        ) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replacement
        temp_path.replace(target_path)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise StorageError(f"Atomic write failed for '{target_path}': {e}") from e
