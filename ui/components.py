"""Reusable Streamlit UI fragments shared across the app's panels."""

from __future__ import annotations

import streamlit as st


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
