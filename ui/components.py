"""Reusable Streamlit UI fragments shared across the app's panels."""

from __future__ import annotations

import html

import streamlit as st

from core.app_launcher import AppEntry
from core.keyboard_layout import KeyboardLayout
from core.launcher_controller import grid_rects


def pill(text: str, kind: str = "neutral") -> str:
    return f'<span class="gb-pill gb-pill-{kind}">{text}</span>'


def header(camera_status: str, camera_kind: str, engine_status: str, engine_kind: str) -> None:
    st.markdown(
        f"""
        <div class="gb-header">
            <div>
                <div class="gb-wordmark">GestureBridge</div>
                <div class="gb-tagline">Your Hands. Your Commands. Your Freedom.</div>
            </div>
            <div style="display:flex; gap:0.5rem;">
                {pill('Camera: ' + camera_status, camera_kind)}
                {pill('Engine: ' + engine_status, engine_kind)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def card_open(title: str) -> None:
    st.markdown(f'<div class="gb-card"><h4>{title}</h4>', unsafe_allow_html=True)


def card_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def stat(label: str, value: str) -> None:
    st.markdown(
        f'<div class="gb-stat-label">{label}</div><div class="gb-big-stat">{value}</div>',
        unsafe_allow_html=True,
    )


def progress_bar(progress: float) -> None:
    pct = max(0.0, min(1.0, progress)) * 100
    st.markdown(
        f'<div class="gb-progress-track"><div class="gb-progress-fill" '
        f'style="width:{pct:.0f}%;"></div></div>',
        unsafe_allow_html=True,
    )


def mapping_row(gesture: str, command: str) -> None:
    st.markdown(
        f'<div class="gb-mapping-row"><span>{gesture.replace("_", " ")}</span>'
        f'<span>&rarr; {command}</span></div>',
        unsafe_allow_html=True,
    )


def keyboard_panel(layout: KeyboardLayout, highlighted_key_id: str | None,
                    pinching: bool, text: str, shift_active: bool, caps_lock: bool) -> None:
    """Renders the virtual QWERTY layout as absolutely-positioned divs
    matching each key's normalized rect, highlighting whichever key the
    pointer is currently over."""
    key_divs = []
    for key in layout.keys:
        is_active = key.id == highlighted_key_id
        css_class = "gb-key"
        if is_active:
            css_class += " gb-key-pinch" if pinching else " gb-key-hover"
        if key.id == "SHIFT" and shift_active:
            css_class += " gb-key-modifier-on"
        if key.id == "CAPS" and caps_lock:
            css_class += " gb-key-modifier-on"
        label = html.escape(key.label)
        style = (
            f"left:{key.x0 * 100:.2f}%; top:{key.y0 * 100:.2f}%; "
            f"width:{(key.x1 - key.x0) * 100:.2f}%; height:{(key.y1 - key.y0) * 100:.2f}%;"
        )
        key_divs.append(f'<div class="{css_class}" style="{style}">{label}</div>')

    display_text = html.escape(text).replace("\n", "<br>") or '<span class="gb-kb-placeholder">Type by pinching over a key…</span>'
    st.markdown(
        f"""
        <div class="gb-kb-textfield">{display_text}</div>
        <div class="gb-keyboard">{''.join(key_divs)}</div>
        """,
        unsafe_allow_html=True,
    )


def action_legend(rows: list[tuple[str, str]], title: str = "What each action does") -> None:
    """A compact gesture -> action legend, e.g. for Mouse/Keyboard mode so
    the mapping is visible without reading the README."""
    row_html = "".join(
        f'<div class="gb-legend-row"><span class="gb-legend-action">{html.escape(action)}</span>'
        f'<span class="gb-legend-arrow">&rarr;</span>'
        f'<span class="gb-legend-effect">{html.escape(effect)}</span></div>'
        for action, effect in rows
    )
    st.markdown(
        f'<div class="gb-legend"><div class="gb-legend-title">{html.escape(title)}</div>{row_html}</div>',
        unsafe_allow_html=True,
    )


def launcher_panel(entries: list[AppEntry], highlighted_id: str | None, pinching: bool) -> None:
    """Renders the app grid, one tile per entry, using the same normalized
    grid geometry launcher_controller.py uses to decide what's under the
    pointer, so the highlight always matches what a pinch would select."""
    rects = grid_rects(len(entries))
    tiles = []
    for entry, (x0, y0, x1, y1) in zip(entries, rects):
        is_active = entry.id == highlighted_id
        css_class = "gb-launcher-tile"
        if not entry.is_available():
            css_class += " gb-launcher-tile-unavailable"
        elif is_active:
            css_class += " gb-launcher-tile-pinch" if pinching else " gb-launcher-tile-hover"
        style = (
            f"left:{x0 * 100:.2f}%; top:{y0 * 100:.2f}%; "
            f"width:{(x1 - x0) * 100:.2f}%; height:{(y1 - y0) * 100:.2f}%;"
        )
        name = html.escape(entry.name)
        tiles.append(
            f'<div class="{css_class}" style="{style}">'
            f'<div class="gb-launcher-icon">{entry.icon}</div>'
            f'<div class="gb-launcher-name">{name}</div></div>'
        )
    st.markdown(f'<div class="gb-launcher-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)
