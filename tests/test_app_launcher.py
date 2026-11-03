"""Unit tests for the app registry and launch validation. Deliberately does
NOT test a successful real launch (that would spawn a real process/window
on whatever machine runs the tests) - only that invalid targets fail safely
and the registry/platform-filtering logic behaves correctly.
"""

import platform

from core.app_launcher import AppEntry, AppRegistry, default_registry, launch


def test_default_registry_has_both_platforms_represented():
    entries = default_registry()
    platforms = {e.platform for e in entries}
    assert "windows" in platforms
    assert "darwin" in platforms


def test_visible_entries_filters_to_current_platform():
    registry = AppRegistry()
    visible = registry.visible_entries()
    system = platform.system()
    want = "windows" if system == "Windows" else ("darwin" if system == "Darwin" else None)
    assert all(e.platform in ("any", want) for e in visible)
    # Sanity: the other platform's entries must be excluded, not just tolerated.
    other = "darwin" if want == "windows" else "windows"
    assert not any(e.platform == other for e in visible)


def test_add_custom_appends_entry_for_current_platform():
    registry = AppRegistry(entries=[])
    entry = registry.add_custom("My Tool", "my_tool.exe")
    assert entry in registry.entries
    assert entry.name == "My Tool"
    system = platform.system()
    expected = "windows" if system == "Windows" else ("darwin" if system == "Darwin" else "any")
    assert entry.platform == expected


def test_remove_drops_the_entry():
    registry = AppRegistry(entries=[])
    entry = registry.add_custom("Temp", "temp.exe")
    registry.remove(entry.id)
    assert entry not in registry.entries


def test_is_available_false_for_entry_targeting_a_different_platform():
    # An entry explicitly scoped to the OTHER platform must never read as
    # available here, regardless of what OS the tests run on.
    other = "darwin" if platform.system() == "Windows" else "windows"
    entry = AppEntry("x", "X", "x", "x", platform=other)
    assert entry.is_available() is False


def test_is_available_false_for_nonexistent_windows_target():
    if platform.system() != "Windows":
        return  # this check is platform-specific; nothing to assert elsewhere
    entry = AppEntry("x", "X", "x", "definitely_not_a_real_exe_xyz123.exe", platform="windows")
    assert entry.is_available() is False


def test_launch_fails_safely_for_nonexistent_target_without_raising():
    entry = AppEntry("x", "Nonexistent", "x", "definitely_not_a_real_exe_xyz123.exe",
                      platform="windows" if platform.system() == "Windows" else "darwin")
    ok, message = launch(entry)
    assert ok is False
    assert isinstance(message, str) and message  # a real, non-empty explanation
