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
    --gb-accent-dim: #2e7a56;
    --gb-warn: #f5c451;
    --gb-danger: #f26d6d;
}

.stApp {
    background-color: var(--gb-bg);
    color: var(--gb-text);
}

.gb-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    background: var(--gb-surface);
    border: 1px solid var(--gb-border);
    border-radius: 16px;
    margin-bottom: 1rem;
}

.gb-wordmark {
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--gb-text);
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

.gb-pill-ok { background: rgba(94,230,164,0.12); color: var(--gb-accent); border-color: var(--gb-accent-dim); }
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
    background: var(--gb-accent);
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
    background: var(--gb-accent);
    color: #0f1115;
    border-color: var(--gb-accent);
    transform: scale(1.08);
}

.gb-key-modifier-on {
    outline: 2px solid var(--gb-warn);
    outline-offset: -2px;
}
</style>
"""
