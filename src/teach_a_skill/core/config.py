"""Configuration alias for core namespace."""

from teach_a_skill.config.defaults import get_default_config
from teach_a_skill.config.manager import ConfigManager
from teach_a_skill.config.schema import AppConfig

__all__ = ["ConfigManager", "get_default_config", "AppConfig"]
