"""A compact QWERTY layout for the spatial keyboard: a flat list of keys,
each with a precomputed normalized (0-1) rectangle within the keyboard
panel. `key_at()` does a simple point-in-rect lookup - cheap enough to run
every frame against ~45 keys.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    id: str
    label: str
    x0: float
    y0: float
    x1: float
    y1: float
    char: str | None = None  # the character this key inserts; None for special keys

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1


def _row(chars: str, y0: float, y1: float, x0: float = 0.0, x1: float = 1.0) -> list[Key]:
    n = len(chars)
    width = (x1 - x0) / n
    keys = []
    for i, ch in enumerate(chars):
        kx0 = x0 + i * width
        keys.append(Key(id=f"CHAR_{ch}", label=ch, x0=kx0, y0=y0, x1=kx0 + width, y1=y1, char=ch))
    return keys


def _build_layout() -> list[Key]:
    keys: list[Key] = []
    keys += _row("1234567890", 0.00, 0.20)
    keys += _row("QWERTYUIOP", 0.20, 0.40)
    keys += _row("ASDFGHJKL", 0.40, 0.60, x0=0.05, x1=0.95)

    # Row 4: Shift | Z X C V B N M | Backspace
    keys.append(Key("SHIFT", "Shift", 0.00, 0.60, 0.15, 0.80))
    keys += _row("ZXCVBNM", 0.60, 0.80, x0=0.15, x1=0.85)
    keys.append(Key("BACKSPACE", "<-", 0.85, 0.60, 1.00, 0.80))

    # Row 5: Caps | Space | Clear | Enter
    keys.append(Key("CAPS", "Caps", 0.00, 0.80, 0.15, 1.00))
    keys.append(Key("SPACE", "Space", 0.15, 0.80, 0.70, 1.00))
    keys.append(Key("CLEAR", "Clear", 0.70, 0.80, 0.85, 1.00))
    keys.append(Key("ENTER", "Enter", 0.85, 0.80, 1.00, 1.00))
    return keys


class KeyboardLayout:
    """A fixed compact QWERTY layout: letters, digits, space, backspace,
    enter, shift (one-shot), caps lock, and clear. No symbol layout or
    punctuation layer yet - see README limitations."""

    def __init__(self):
        self.keys: list[Key] = _build_layout()
        self._by_id = {k.id: k for k in self.keys}

    def key_at(self, x: float, y: float) -> Key | None:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        for key in self.keys:
            if key.contains(x, y):
                return key
        return None

    def get(self, key_id: str) -> Key | None:
        return self._by_id.get(key_id)
