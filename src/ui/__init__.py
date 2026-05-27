"""User-interface layer for Sift.

Contains display helpers (``display.py``), the first-run setup wizard
(``setup.py``), the interactive main menu (``menu.py``), and design
tokens (``theme.py``).
"""

from src.ui.display import (
    console,
    print_banner,
    print_large_banner,
)
from src.ui.setup import is_configured, run_setup_wizard
from src.ui.menu import run_main_menu
from src.ui.theme import (
    ACCENT_COLOR,
    AMBER,
    CYAN,
    EMERALD,
    ICON_DONE,
    ICON_WARN,
    ROSE,
    SEVERITY_COLORS,
    SEVERITY_DOTS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    VIOLET,
)

__all__ = [
    "console",
    "print_banner",
    "print_large_banner",
    "is_configured",
    "run_setup_wizard",
    "run_main_menu",
    "ACCENT_COLOR",
    "AMBER",
    "CYAN",
    "EMERALD",
    "ICON_DONE",
    "ICON_WARN",
    "ROSE",
    "SEVERITY_COLORS",
    "SEVERITY_DOTS",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "VIOLET",
]
