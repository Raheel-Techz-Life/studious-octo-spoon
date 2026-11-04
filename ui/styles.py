"""Centralized visual styling.

A HUD/terminal look (sharp corners, bracket-cornered panels, monospace
labels, cyan/magenta duotone) instead of the generic rounded-card dark
dashboard most AI-scaffolded Streamlit apps default to. Every class name
here is unchanged from the original theme - only declarations changed -
so ui/components.py and app.py needed zero edits.
"""

CSS = """
<style>
:root {
    --gb-bg: #05070a;
    --gb-surface: #0b0f16;
    --gb-surface-alt: #10151f;
    --gb-border: #1f2a3a;
    --gb-text: #e8f2ff;
    --gb-text-dim: #7489a6;
    --gb-accent: #00e5c7;
    --gb-accent2: #ff2fb0;
    --gb-accent-dim: #0a5c53;
    --gb-warn: #ffb020;
    --gb-danger: #ff3b5c;
    --gb-mono: "JetBrains Mono", ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
}

.stApp {
    background:
        repeating-linear-gradient(0deg, rgba(0,229,199,0.025) 0px, rgba(0,229,199,0.025) 1px, transparent 1px, transparent 3px),
        radial-gradient(900px 500px at 90% -10%, rgba(255,47,176,0.07), transparent 55%),
        radial-gradient(900px 500px at -10% 0%, rgba(0,229,199,0.08), transparent 55%),
        var(--gb-bg);
    color: var(--gb-text);
}

.stApp, .stApp p, .stApp span, .stApp label {
    font-family: "Inter", ui-sans-serif, system-ui, sans-serif;
}

[data-testid="stSidebar"] {
    background: var(--gb-surface);
    border-right: 1px solid var(--gb-border);
}

[data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {
    font-family: var(--gb-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.85rem;
    color: var(--gb-accent);
}

.stButton > button {
    border-radius: 3px !important;
    border: 1px solid var(--gb-border) !important;
    background: var(--gb-surface-alt) !important;
    color: var(--gb-text) !important;
    font-family: var(--gb-mono) !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    font-size: 0.78rem !important;
    transition: border-color 0.12s ease, box-shadow 0.12s ease !important;
}
.stButton > button:hover {
    border-color: var(--gb-accent) !important;
    box-shadow: 0 0 0 1px var(--gb-accent) inset, 0 0 14px rgba(0,229,199,0.25) !important;
    color: var(--gb-accent) !important;
}

/* Sliders / toggles: swap Streamlit's default red for the accent duo */
[data-testid="stSlider"] [role="slider"] {
    background-color: var(--gb-accent) !important;
    box-shadow: 0 0 10px rgba(0,229,199,0.5) !important;
}
[data-testid="stSlider"] div[data-baseweb="slider"] > div > div {
    background: linear-gradient(90deg, var(--gb-accent), var(--gb-accent2)) !important;
}
[data-testid="stCheckbox"] [role="checkbox"][aria-checked="true"],
label[data-baseweb="checkbox"] span {
    background-color: var(--gb-accent-dim) !important;
}
[data-baseweb="radio"] div:first-child {
    border-color: var(--gb-border) !important;
}

.gb-header {
    position: relative;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 1.1rem 1.5rem;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 2px;
    margin-bottom: 1rem;
    overflow: visible;
    clip-path: polygon(0 14px, 14px 0, 100% 0, 100% calc(100% - 14px), calc(100% - 14px) 100%, 0 100%);
}

.gb-header::before, .gb-header::after {
    content: "";
    position: absolute;
    width: 20px;
    height: 20px;
    border: 2px solid var(--gb-accent);
}
.gb-header::before { top: -2px; left: -2px; border-right: none; border-bottom: none; }
.gb-header::after { bottom: -2px; right: -2px; border-left: none; border-top: none; border-color: var(--gb-accent2); }

.gb-wordmark {
    font-family: var(--gb-mono);
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--gb-text);
    text-shadow: 0 0 18px rgba(0,229,199,0.35), 2px 0 0 rgba(255,47,176,0.25);
}

.gb-tagline {
    color: var(--gb-text-dim);
    font-size: 0.82rem;
    font-family: var(--gb-mono);
    letter-spacing: 0.03em;
}
.gb-tagline::before { content: "> "; color: var(--gb-accent); }

.gb-card {
    position: relative;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-left: 2px solid var(--gb-accent-dim);
    border-radius: 2px;
    padding: 1.1rem 1.25rem;
    margin-bottom: 1rem;
    transition: border-left-color 0.15s ease;
}
.gb-card:hover {
    border-left-color: var(--gb-accent);
}

.gb-card h4 {
    margin-top: 0;
    font-family: var(--gb-mono);
    font-size: 0.78rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--gb-text-dim);
}

.gb-pill {
    display: inline-block;
    padding: 0.22rem 0.7rem;
    border-radius: 2px;
    font-family: var(--gb-mono);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border: 1px solid var(--gb-border);
}

.gb-pill-ok { background: rgba(0,229,199,0.1); color: var(--gb-accent); border-color: var(--gb-accent-dim); box-shadow: 0 0 10px rgba(0,229,199,0.18); }
.gb-pill-warn { background: rgba(255,176,32,0.1); color: var(--gb-warn); border-color: #7a4e0e; }
.gb-pill-danger { background: rgba(255,59,92,0.1); color: var(--gb-danger); border-color: #7a1d30; }
.gb-pill-neutral { background: var(--gb-surface-alt); color: var(--gb-text-dim); }

.gb-big-stat {
    font-family: var(--gb-mono);
    font-size: 2rem;
    font-weight: 700;
    color: var(--gb-text);
}

.gb-stat-label {
    color: var(--gb-text-dim);
    font-size: 0.72rem;
    font-family: var(--gb-mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

.gb-progress-track {
    width: 100%;
    height: 6px;
    background: var(--gb-surface-alt);
    border-radius: 0;
    overflow: hidden;
    border: 1px solid var(--gb-border);
}

.gb-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--gb-accent), var(--gb-accent2));
    box-shadow: 0 0 8px rgba(0,229,199,0.5);
    transition: width 0.1s linear;
}

.gb-mapping-row {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px dashed var(--gb-border);
    font-family: var(--gb-mono);
    font-size: 0.85rem;
}
.gb-mapping-row:last-child { border-bottom: none; }

.gb-kb-textfield {
    min-height: 2.6rem;
    background: #000;
    border: 1px solid var(--gb-accent-dim);
    border-radius: 2px;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.6rem;
    font-size: 1.05rem;
    font-family: var(--gb-mono);
    color: var(--gb-accent);
    white-space: pre-wrap;
    word-break: break-word;
}
.gb-kb-textfield::after {
    content: "_";
    animation: gb-blink 1s step-end infinite;
}
@keyframes gb-blink { 50% { opacity: 0; } }

.gb-kb-placeholder {
    color: var(--gb-text-dim);
    font-style: normal;
}

.gb-keyboard {
    position: relative;
    width: 100%;
    aspect-ratio: 2.4 / 1;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 2px;
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
    font-family: var(--gb-mono);
    font-size: 0.82rem;
    font-weight: 600;
    transition: background 0.08s ease, color 0.08s ease, transform 0.08s ease;
    user-select: none;
}

.gb-key-hover {
    background: rgba(0, 229, 199, 0.14);
    color: var(--gb-text);
    border-color: var(--gb-accent);
    transform: scale(1.04);
}

.gb-key-pinch {
    background: var(--gb-accent);
    color: #05070a;
    border-color: var(--gb-accent);
    transform: scale(1.08);
    box-shadow: 0 0 18px rgba(0,229,199,0.55);
}

.gb-key-modifier-on {
    outline: 2px solid var(--gb-accent2);
    outline-offset: -2px;
}

.gb-launcher-grid {
    position: relative;
    width: 100%;
    aspect-ratio: 2.2 / 1;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 2px;
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
.gb-launcher-name { font-family: var(--gb-mono); font-size: 0.76rem; font-weight: 600; text-align: center; padding: 0 0.3rem; }

.gb-launcher-tile-hover {
    background: rgba(0, 229, 199, 0.14);
    color: var(--gb-text);
    border-color: var(--gb-accent);
    transform: scale(1.04);
}

.gb-launcher-tile-pinch {
    background: var(--gb-accent);
    color: #05070a;
    border-color: var(--gb-accent);
    transform: scale(1.08);
    box-shadow: 0 0 18px rgba(0,229,199,0.55);
}

.gb-launcher-tile-unavailable {
    opacity: 0.3;
}

.gb-legend {
    background: var(--gb-surface-alt);
    border: 1px solid var(--gb-border);
    border-left: 2px solid var(--gb-accent2);
    border-radius: 2px;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.6rem;
}

.gb-legend-title {
    font-family: var(--gb-mono);
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
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
    border-bottom: 1px dashed var(--gb-border);
}
.gb-legend-row:last-child { border-bottom: none; }

.gb-legend-action { color: var(--gb-text); font-weight: 600; }
.gb-legend-arrow { color: var(--gb-accent); font-family: var(--gb-mono); }
.gb-legend-effect { color: var(--gb-text-dim); text-align: right; font-family: var(--gb-mono); }
</style>
"""
