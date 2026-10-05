"""Storage subsystem."""

from teach_a_skill.storage.atomic import atomic_write
from teach_a_skill.storage.manager import StorageManager

__all__ = ["StorageManager", "atomic_write"]
