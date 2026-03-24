"""Accessible colour palette for the AIGate CLI.

Design goals
────────────
• Readable on dark *and* light terminal backgrounds
• Deuteranopia / protanopia (red-green colour-blind) safe
  – every status uses a symbol (✓ ✗ ● ▸) alongside colour
  – warn is orange (not yellow/green) to separate from success/error
• All colours differ enough in luminance to remain distinguishable
  even in greyscale (e.g. reduced-colour modes)
• Single source-of-truth imported by every CLI module
"""

from __future__ import annotations

import questionary
from rich.console import Console
from rich.theme import Theme

# ── Hex values (reusable in prompt_toolkit / questionary) ────────────
HEX_SUCCESS = "#78d97b"   # bright green  — paired with ✓
HEX_ERROR   = "#ff6b6b"   # coral red     — paired with ✗
HEX_WARN    = "#ffa657"   # orange        — safe vs red & green for CVD
HEX_ACCENT  = "#6ea8fe"   # bright blue   — replaces hard-to-read cyan
HEX_MUTED   = "#888888"   # neutral gray  — secondary / dimmed text
HEX_VALUE   = "#e2e2e2"   # near-white    — high-contrast values
HEX_PURPLE  = "#c49bff"   # light purple  — LLM / special items

# ── Rich theme (use [success], [error], … in markup) ────────────────
RICH_THEME = Theme({
    "success": HEX_SUCCESS,
    "error":   HEX_ERROR,
    "warn":    HEX_WARN,
    "accent":  HEX_ACCENT,
    "muted":   HEX_MUTED,
    "value":   HEX_VALUE,
    "purple":  HEX_PURPLE,
})

console = Console(theme=RICH_THEME)

# ── Questionary prompt style ────────────────────────────────────────
PROMPT_STYLE = questionary.Style([
    ("qmark",       f"fg:{HEX_ACCENT} bold"),
    ("question",    "bold"),
    ("answer",      f"fg:{HEX_SUCCESS} bold"),
    ("pointer",     f"fg:{HEX_ACCENT} bold"),
    ("highlighted", f"fg:{HEX_ACCENT} bold"),
    ("selected",    f"fg:{HEX_SUCCESS}"),
])

# ── Severity / Action colour maps (TUI + general use) ───────────────
SEVERITY_COLORS: dict[str, str] = {
    "critical": HEX_ERROR,
    "high":     HEX_WARN,
    "medium":   "#ffcc44",
    "low":      HEX_ACCENT,
    "info":     HEX_MUTED,
}

ACTION_COLORS: dict[str, str] = {
    "block":    HEX_ERROR,
    "sanitize": "#ffcc44",
    "warn":     HEX_WARN,
    "log":      HEX_ACCENT,
    "pass":     HEX_MUTED,
}

# ── prompt_toolkit TUI style dict (shield configurator) ─────────────
TUI_STYLE_DICT: dict[str, str] = {
    "brand":     "bg:#1a5fb4 #ffffff bold",
    "title":     "#ffffff bold",
    "bar":       "#555555",
    "rule":      "#444444",
    "colhdr":    "#aaaaaa bold",
    "section":   f"{HEX_ACCENT} bold",
    "name":      "#ffffff",
    "label":     "#cccccc",
    "key":       f"bg:#333333 {HEX_ACCENT} bold",
    "hint":      "#999999",
    "ptr":       f"{HEX_ACCENT} bold",
    "on":        f"{HEX_SUCCESS} bold",
    "off":       HEX_ERROR,
    "mod":       HEX_WARN,
    "dim":       "#999999",
    "status":    HEX_WARN,
    "sel":       "bg:#1e3a5f",
    "sel on":    f"bg:#1e3a5f {HEX_SUCCESS} bold",
    "sel off":   f"bg:#1e3a5f {HEX_ERROR}",
    "sel name":  "bg:#1e3a5f #ffffff bold",
    "sel ptr":   f"bg:#1e3a5f {HEX_ACCENT} bold",
    "sel label": "bg:#1e3a5f #dddddd",
    "sel mod":   f"bg:#1e3a5f {HEX_WARN}",
    "sel dim":   "bg:#1e3a5f #aaaaaa",
}
