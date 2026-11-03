"""A small, explicitly-configured registry of launchable applications, and
a safe launch function.

Safety: targets are never built from gesture labels or any recognition
output - they come only from this fixed default list or from paths the
user typed into the sidebar. Launching never goes through a shell string;
Windows uses `os.startfile` (the same mechanism as double-clicking in
Explorer) and macOS uses `subprocess.Popen(["open", "-a", name])` with an
explicit argument list, never `shell=True`. A target is validated
(resolvable via PATH or an existing file) before it is offered as
selectable, and re-validated at launch time.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class AppEntry:
    id: str
    name: str
    icon: str
    target: str  # Windows: an exe name resolvable on PATH, or an absolute path.
                 # macOS: an application name passed to `open -a`.
    platform: str = "any"  # "windows", "darwin", or "any"

    def is_available(self) -> bool:
        system = platform.system()
        if self.platform == "windows" and system != "Windows":
            return False
        if self.platform == "darwin" and system != "Darwin":
            return False
        if system == "Windows":
            return bool(shutil.which(self.target) or os.path.isfile(self.target))
        if system == "Darwin":
            # Can't cheaply verify an app bundle exists without launching it;
            # treat macOS entries as available and let launch() report failure.
            return True
        return False


def default_registry() -> list[AppEntry]:
    return [
        AppEntry("notepad", "Notepad", "📝", "notepad.exe", platform="windows"),
        AppEntry("calculator", "Calculator", "🧮", "calc.exe", platform="windows"),
        AppEntry("explorer", "File Explorer", "📁", "explorer.exe", platform="windows"),
        AppEntry("paint", "Paint", "🎨", "mspaint.exe", platform="windows"),
        AppEntry("mac_calculator", "Calculator", "🧮", "Calculator", platform="darwin"),
        AppEntry("mac_textedit", "TextEdit", "📝", "TextEdit", platform="darwin"),
        AppEntry("mac_finder", "Finder", "📁", "Finder", platform="darwin"),
    ]


class AppRegistry:
    def __init__(self, entries: list[AppEntry] | None = None):
        self.entries: list[AppEntry] = entries if entries is not None else default_registry()

    def visible_entries(self) -> list[AppEntry]:
        """Only entries relevant to the current OS, in display order."""
        system = platform.system()
        want = "windows" if system == "Windows" else ("darwin" if system == "Darwin" else None)
        return [e for e in self.entries if e.platform == "any" or e.platform == want]

    def add_custom(self, name: str, target: str, icon: str = "⭐") -> AppEntry:
        system = platform.system()
        plat = "windows" if system == "Windows" else ("darwin" if system == "Darwin" else "any")
        entry = AppEntry(id=f"custom_{len(self.entries)}", name=name, icon=icon,
                          target=target, platform=plat)
        self.entries.append(entry)
        return entry

    def remove(self, entry_id: str) -> None:
        self.entries = [e for e in self.entries if e.id != entry_id]


def launch(entry: AppEntry) -> tuple[bool, str]:
    """Launches an app entry. Never uses a shell string; validates the
    target right before launching, not just at selection time."""
    system = platform.system()
    try:
        if system == "Windows":
            resolved = shutil.which(entry.target) or (entry.target if os.path.isfile(entry.target) else None)
            if not resolved:
                return False, f"Could not find '{entry.target}' on this system."
            os.startfile(resolved)  # noqa: S606 - explicit, validated target; not a shell string
            return True, f"Launched {entry.name}"
        elif system == "Darwin":
            result = subprocess.run(["open", "-a", entry.target], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False, f"Failed to launch {entry.name}: {result.stderr.strip() or 'unknown error'}"
            return True, f"Launched {entry.name}"
        else:
            return False, f"App launching is not supported on {system}."
    except Exception as exc:  # noqa: BLE001
        return False, f"Failed to launch {entry.name}: {exc}"
