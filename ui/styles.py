"""Centralized visual styling: a dark, high-contrast accessibility-focused theme."""

CSS = """
<style>
:root {
    --gb-bg: #0f1115;
    --gb-surface: #171a21;
    --gb-surface-alt: #1e222b;
    --gb-border: #2b3040;
    --gb-text: #f2f4f8;
    --gb-text-dim: #a8afc0;
    --gb-accent: #5ee6a4;
    --gb-accent2: #4ac4ff;
    --gb-accent-dim: #2e7a56;
    --gb-warn: #f5c451;
    --gb-danger: #f26d6d;
}

.stApp {
    background:
        radial-gradient(1200px 600px at 85% -10%, rgba(74,196,255,0.08), transparent 60%),
        radial-gradient(1000px 500px at -10% 10%, rgba(94,230,164,0.07), transparent 55%),
        var(--gb-bg);
    color: var(--gb-text);
}

.stButton > button {
    border-radius: 10px !important;
    border: 1px solid var(--gb-border) !important;
    transition: transform 0.08s ease, border-color 0.15s ease !important;
}
.stButton > button:hover {
    border-color: var(--gb-accent-dim) !important;
    transform: translateY(-1px);
}

.gb-header {
    position: relative;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 1.1rem 1.4rem;
    background: linear-gradient(145deg, var(--gb-surface), var(--gb-surface-alt));
    border: 1px solid var(--gb-border);
    border-radius: 18px;
    margin-bottom: 1rem;
    overflow: hidden;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
}

.gb-header::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 3px;
    background: linear-gradient(90deg, var(--gb-accent), var(--gb-accent2));
}

.gb-wordmark {
    font-size: 1.75rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, var(--gb-text) 30%, var(--gb-accent) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}

.gb-tagline {
    color: var(--gb-text-dim);
    font-size: 0.95rem;
}

.gb-card {
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 16px;
    padding: 1.1rem 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 14px rgba(0,0,0,0.18);
    transition: border-color 0.15s ease;
}
.gb-card:hover {
    border-color: var(--gb-accent-dim);
}

.gb-card h4 {
    margin-top: 0;
    color: var(--gb-text);
    font-size: 1rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--gb-text-dim);
}

.gb-pill {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1px solid var(--gb-border);
}

.gb-pill-ok { background: rgba(94,230,164,0.12); color: var(--gb-accent); border-color: var(--gb-accent-dim); box-shadow: 0 0 12px rgba(94,230,164,0.15); }
.gb-pill-warn { background: rgba(245,196,81,0.12); color: var(--gb-warn); border-color: #8a6a1f; }
.gb-pill-danger { background: rgba(242,109,109,0.12); color: var(--gb-danger); border-color: #8a2f2f; }
.gb-pill-neutral { background: var(--gb-surface-alt); color: var(--gb-text-dim); }

.gb-big-stat {
    font-size: 2.2rem;
    font-weight: 800;
    color: var(--gb-text);
}

.gb-stat-label {
    color: var(--gb-text-dim);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.gb-progress-track {
    width: 100%;
    height: 10px;
    background: var(--gb-surface-alt);
    border-radius: 999px;
    overflow: hidden;
    border: 1px solid var(--gb-border);
}

.gb-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--gb-accent), var(--gb-accent2));
    transition: width 0.1s linear;
}

.gb-mapping-row {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--gb-border);
    font-size: 0.95rem;
}
.gb-mapping-row:last-child { border-bottom: none; }

.gb-kb-textfield {
    min-height: 2.6rem;
    background: var(--gb-surface-alt);
    border: 1px solid var(--gb-border);
    border-radius: 10px;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.6rem;
    font-size: 1.1rem;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    color: var(--gb-text);
    white-space: pre-wrap;
    word-break: break-word;
}

.gb-kb-placeholder {
    color: var(--gb-text-dim);
    font-style: italic;
}

.gb-keyboard {
    position: relative;
    width: 100%;
    aspect-ratio: 2.4 / 1;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 12px;
    overflow: hidden;
}

.gb-key {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
    border: 1px solid var(--gb-border);
    background: var(--gb-surface-alt);
    color: var(--gb-text-dim);
    font-size: 0.85rem;
    font-weight: 600;
    transition: background 0.08s ease, color 0.08s ease, transform 0.08s ease;
    user-select: none;
}

.gb-key-hover {
    background: rgba(94, 230, 164, 0.18);
    color: var(--gb-text);
    border-color: var(--gb-accent-dim);
    transform: scale(1.04);
}

.gb-key-pinch {
    background: linear-gradient(135deg, var(--gb-accent), var(--gb-accent2));
    color: #0f1115;
    border-color: var(--gb-accent);
    transform: scale(1.08);
    box-shadow: 0 0 16px rgba(94,230,164,0.35);
}

.gb-key-modifier-on {
    outline: 2px solid var(--gb-warn);
    outline-offset: -2px;
}

.gb-launcher-grid {
    position: relative;
    width: 100%;
    aspect-ratio: 2.2 / 1;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 12px;
    overflow: hidden;
}

.gb-launcher-tile {
    position: absolute;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.3rem;
    box-sizing: border-box;
    border: 1px solid var(--gb-border);
    background: var(--gb-surface-alt);
    color: var(--gb-text-dim);
    transition: background 0.08s ease, color 0.08s ease, transform 0.08s ease;
    user-select: none;
}

.gb-launcher-icon { font-size: 1.8rem; line-height: 1; }
.gb-launcher-name { font-size: 0.8rem; font-weight: 600; text-align: center; padding: 0 0.3rem; }

.gb-launcher-tile-hover {
    background: rgba(94, 230, 164, 0.18);
    color: var(--gb-text);
    border-color: var(--gb-accent-dim);
    transform: scale(1.04);
}

.gb-launcher-tile-pinch {
    background: linear-gradient(135deg, var(--gb-accent), var(--gb-accent2));
    color: #0f1115;
    border-color: var(--gb-accent);
    transform: scale(1.08);
    box-shadow: 0 0 16px rgba(94,230,164,0.35);
}

.gb-launcher-tile-unavailable {
    opacity: 0.35;
}

.gb-legend {
    background: var(--gb-surface-alt);
    border: 1px solid var(--gb-border);
    border-radius: 10px;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.6rem;
}

.gb-legend-title {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--gb-text-dim);
    margin-bottom: 0.4rem;
}

.gb-legend-row {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0;
    font-size: 0.85rem;
    border-bottom: 1px solid var(--gb-border);
}
.gb-legend-row:last-child { border-bottom: none; }

.gb-legend-action { color: var(--gb-text); font-weight: 600; }
.gb-legend-arrow { color: var(--gb-accent); }
.gb-legend-effect { color: var(--gb-text-dim); text-align: right; }
</style>
"""
