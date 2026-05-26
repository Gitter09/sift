"""User-interface layer for Sift.

Contains display helpers (``display.py``), the first-run setup wizard
(``setup.py``), and the interactive main menu (``menu.py``).
"""

from src.ui.display import (
    console,
    print_banner,
    print_large_banner,
)
from src.ui.setup import is_configured, run_setup_wizard
from src.ui.menu import run_main_menu

__all__ = [
    "console",
    "print_banner",
    "print_large_banner",
    "is_configured",
    "run_setup_wizard",
    "run_main_menu",
]
