"""Keyboard event representation, modifiers, and shortcut reconstruction."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class KeyAction(str, Enum):
    DOWN = "DOWN"
    UP = "UP"
    TEXT = "TEXT"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class KeyEventPayload:
    """Normalized keyboard interaction event."""

    key: str  # Human readable key name (e.g. 'a', 'Return', 'Control_L', 'ArrowUp')
    action: KeyAction
    code: Optional[str] = None  # Physical keycode/scancode if provided by OS
    modifiers: list[str] = field(default_factory=list)  # e.g. ["ctrl", "shift"]
    is_shortcut: bool = False
    shortcut_string: Optional[str] = None  # e.g. "Ctrl+Shift+P"
    text: Optional[str] = None  # Produced text if separate text event

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = str(self.action)
        return data


class ShortcutReconstructor:
    """Tracks active modifiers to identify and reconstruct keyboard shortcuts."""

    MODIFIER_KEYS = {
        "ctrl": "ctrl",
        "control": "ctrl",
        "control_l": "ctrl",
        "control_r": "ctrl",
        "shift": "shift",
        "shift_l": "shift",
        "shift_r": "shift",
        "alt": "alt",
        "alt_l": "alt",
        "alt_r": "alt",
        "option": "alt",
        "cmd": "cmd",
        "command": "cmd",
        "super": "cmd",
        "meta": "cmd",
        "win": "cmd",
    }

    def __init__(self) -> None:
        self._active_modifiers: set[str] = set()

    def process_key_event(self, key: str, action: KeyAction) -> KeyEventPayload:
        """Update modifier tracking and build a normalized KeyEventPayload."""
        normalized_key = key.strip()
        key_lower = normalized_key.lower()

        is_modifier = key_lower in self.MODIFIER_KEYS
        mod_canonical = self.MODIFIER_KEYS.get(key_lower)

        if action == KeyAction.DOWN and is_modifier and mod_canonical:
            self._active_modifiers.add(mod_canonical)
        elif action == KeyAction.UP and is_modifier and mod_canonical:
            self._active_modifiers.discard(mod_canonical)

        mods_list = sorted(self._active_modifiers)

        # A shortcut is active if a non-modifier key is pressed DOWN while modifiers are held
        is_shortcut = False
        shortcut_str: Optional[str] = None

        if action == KeyAction.DOWN and not is_modifier and len(mods_list) > 0:
            is_shortcut = True
            # Build shortcut string: e.g. "Ctrl+Shift+P"
            parts = [m.capitalize() for m in mods_list]
            parts.append(normalized_key.upper() if len(normalized_key) == 1 else normalized_key)
            shortcut_str = "+".join(parts)

        return KeyEventPayload(
            key=normalized_key,
            action=action,
            modifiers=mods_list,
            is_shortcut=is_shortcut,
            shortcut_string=shortcut_str,
        )

    def reset(self) -> None:
        """Reset internal modifier state upon recording pause/stop."""
        self._active_modifiers.clear()
