"""PlatformManager unifying host detection, simulated platform execution, and path normalization."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Optional

from teach_a_skill.core.errors import TeachSkillError
from teach_a_skill.platform.base import BasePlatformAdapter
from teach_a_skill.platform.capabilities import (
    CapabilityState,
    PlatformCapabilities,
    PlatformCapability,
    PlatformCompatibilityManifest,
)
from teach_a_skill.platform.linux import LinuxAdapter, LinuxPlatformAdapter
from teach_a_skill.platform.macos import MacOSAdapter, MacOSPlatformAdapter
from teach_a_skill.platform.windows import WindowsAdapter, WindowsPlatformAdapter


class PlatformManager:
    """Manages cross-platform adapter resolution, simulated testing, and portable path normalization."""

    @classmethod
    def get_current_platform_name(cls) -> str:
        sys_name = platform.system().lower()
        if sys_name == "darwin":
            return "macos"
        elif sys_name == "linux":
            return "linux"
        elif sys_name == "windows":
            return "windows"
        return sys_name

    @classmethod
    def get_adapter(cls, target_os: Optional[str] = None) -> BasePlatformAdapter:
        """Resolve live or simulated platform adapter."""
        os_key = (target_os or cls.get_current_platform_name()).lower()
        if os_key in ("darwin", "macos", "osx"):
            return MacOSPlatformAdapter()
        elif os_key == "linux":
            return LinuxPlatformAdapter()
        elif os_key in ("windows", "win32", "nt"):
            return WindowsPlatformAdapter()
        else:
            raise TeachSkillError(f"Unsupported operating system target: '{target_os}'")

    @classmethod
    def normalize_path_to_logical(cls, raw_path: str, base_dir: Optional[str] = None) -> str:
        """Strip host-specific absolute paths to logical references for portable skill preservation."""
        if not raw_path:
            return ""

        # Normalize slashes
        norm = raw_path.replace("\\", "/")

        # Check against base dir if provided
        if base_dir:
            base_norm = str(Path(base_dir).resolve()).replace("\\", "/")
            if norm.startswith(base_norm):
                rel = norm[len(base_norm):].lstrip("/")
                return f"<app_data>/{rel}"

        # Check common system prefixes
        home_norm = str(Path.home()).replace("\\", "/")
        if norm.startswith(home_norm):
            rel = norm[len(home_norm):].lstrip("/")
            return f"<user_home>/{rel}"

        # Standard Windows drive letters
        if len(norm) >= 2 and norm[1] == ":":
            return f"<volume>/{norm[3:]}"

        return norm

    @classmethod
    def resolve_logical_path(cls, logical_path: str, base_dir: str) -> Path:
        """Resolve a portable logical path back to the active host's concrete filesystem path."""
        if not logical_path:
            return Path(base_dir)

        norm = logical_path.replace("\\", "/")
        if norm.startswith("<app_data>/"):
            sub = norm[len("<app_data>/"):]
            return Path(base_dir) / sub
        elif norm.startswith("<user_home>/"):
            sub = norm[len("<user_home>/"):]
            return Path.home() / sub

        return Path(logical_path)
