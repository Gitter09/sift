"""Design tokens for the Sift CLI — the single source of truth for color,
typography, and symbols used across the entire UI layer.

Every module in ``src.ui`` should pull its Rich styling from here to
keep the visual language consistent.
"""

from __future__ import annotations

# ── Palette ─────────────────────────────────────────────────────────────
# Named with user-facing intent, not raw hex values.

# Brand
VIOLET = "#8B5CF6"      # primary accent — banner, borders, brand identity
VIOLET_DIM = "#7C3AED"   # deeper shade for gradient stops and hover states

# Interactive / Progress
CYAN = "#06B6D4"         # active spinner, selection indicators, live state
CYAN_DIM = "#0891B2"     # subdued cyan for secondary progress

# Severity & Status
EMERALD = "#10B981"      # success, completion, "low" severity
AMBER = "#F59E0B"        # warnings, "medium" severity, cautions
ROSE = "#F43F5E"         # errors, "high" severity, failures

# Text
TEXT_PRIMARY = "#F8FAFC"    # main body, headings, labels
TEXT_SECONDARY = "#94A3B8"  # metadata, hints, dimmed content
TEXT_MUTED = "#64748B"      # very subdued — footer hints, disabled states

# Surfaces
BORDER_DEFAULT = VIOLET      # primary panel / table borders
BORDER_MUTED = "#475569"     # subtle dividers, secondary borders
BORDER_DIM = "#334155"       # very faint rules, context separators

# Legacy aliases for compatibility
ACCENT_COLOR = VIOLET
SOURCE_COLOR = "#E2E8F0"  # source names — stand out slightly from body text

# ── Severity Mappings ───────────────────────────────────────────────────

SEVERITY_COLORS = {
    "high": ROSE,
    "medium": AMBER,
    "low": EMERALD,
}

SEVERITY_DOTS = {
    "high": f"[{ROSE}]●[/{ROSE}]",
    "medium": f"[{AMBER}]●[/{AMBER}]",
    "low": f"[{EMERALD}]●[/{EMERALD}]",
}

# ── Aurora Gradient (brand banner) ──────────────────────────────────────
# 7 stops, one per shape row — violet top fading to deep purple bottom.

AURORA_STOPS = [
    "#A78BFA",  # row 0  violet-400 (top)
    "#9B79F7",  # row 1
    "#8F67F4",  # row 2
    "#8355F1",  # row 3
    "#7743EE",  # row 4
    "#6B31EB",  # row 5
    "#5F1FE8",  # row 6  deep violet-purple (bottom)
]

# ── Symbols ─────────────────────────────────────────────────────────────
# Unicode glyphs — no emojis, for a precise desktop-tool aesthetic.

ICON_DONE = "✓"
ICON_WARN = "—"
ICON_SELECT = "›"
ICON_BULLET = "→"
ICON_DIAMOND = "◈"
ICON_DOT = "·"
