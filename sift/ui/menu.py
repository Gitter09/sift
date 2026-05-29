"""Interactive main menu for Sift.

Shown when ``sift`` is run with no subcommand. Provides an arrow-key
navigable menu to launch analysis, scraping, or reconfigure API keys.
"""

from __future__ import annotations

import time

from dotenv import load_dotenv
from rich.panel import Panel
from rich.prompt import Prompt

from sift.ui._terminal import (
    confirm_with_escape,
    console,
    cursor_up,
    hide_cursor,
    read_key,
    read_line_with_escape,
    show_cursor,
)
from sift.ui.display import print_large_banner, VERSION, _git_info
from sift.ui.theme import (
    AMBER,
    CYAN,
    ICON_DOT,
    ICON_SELECT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    VIOLET,
)
from sift.ui.setup import run_setup_wizard
from sift.config import load_settings
from sift.scrapers.factory import AVAILABLE_SOURCES, default_sources

_MENU_LABELS = [
    "Analyze a product",
    "Scrape a product (no analysis)",
    "Settings & API keys",
    "Exit",
]

# Lines printed by _render_menu(): borderx2 + paddingx2 + items + hint
_MENU_TOTAL_LINES = len(_MENU_LABELS) + 4 + 1


def _render_menu(current: int) -> None:
    lines = []
    for i, label in enumerate(_MENU_LABELS):
        if i == current:
            lines.append(f"   [bold {CYAN}]{ICON_SELECT}  {label}[/bold {CYAN}]")
        else:
            lines.append(f"      {label}")

    git = _git_info()
    border_title = (
        f"[{VIOLET}]SIFT  v{VERSION}  {ICON_DOT}  {git}[/{VIOLET}]"
        if git
        else f"[{VIOLET}]SIFT  v{VERSION}[/{VIOLET}]"
    )
    console.print(
        Panel(
            "\n".join(lines),
            title=border_title,
            title_align="center",
            border_style=VIOLET,
            padding=(1, 2),
        )
    )
    console.print(
        f"  [{VIOLET}]\u2191 \u2193[/{VIOLET}]  "
        f"[{TEXT_MUTED}]navigate[/{TEXT_MUTED}]  {ICON_DOT}  "
        f"enter  [{TEXT_SECONDARY}]select[/{TEXT_SECONDARY}]  {ICON_DOT}  "
        f"q  [{TEXT_MUTED}]quit[/{TEXT_MUTED}]  {ICON_DOT}  "
        f"Esc  [{TEXT_MUTED}]back[/{TEXT_MUTED}]"
    )


def _render_sub_header(title: str, subtitle: str) -> None:
    """Render a sub-page header with a violet-bordered panel."""
    git = _git_info()
    border_title = (
        f"[{TEXT_MUTED}]SIFT  v{VERSION}  {ICON_DOT}  {git}[/{TEXT_MUTED}]"
        if git
        else f"[{TEXT_MUTED}]SIFT  v{VERSION}[/{TEXT_MUTED}]"
    )
    console.print(
        Panel(
            f"[bold {TEXT_PRIMARY}]{title}[/bold {TEXT_PRIMARY}]\n"
            f"[{TEXT_SECONDARY}]{subtitle}[/{TEXT_SECONDARY}]",
            title=border_title,
            title_align="center",
            border_style=VIOLET,
        )
    )
    console.print()


def run_main_menu() -> None:
    """Main interactive loop: show banner, navigate menu with arrow keys."""
    current = 0
    try:
        while True:
            console.clear()
            print_large_banner()
            _render_menu(current)

            # Hide cursor only during arrow-key navigation, since the options
            # menu has nothing to type. Restore it before any text prompt.
            hide_cursor()
            try:
                while True:
                    key = read_key()
                    if key == 'up':
                        current = (current - 1) % len(_MENU_LABELS)
                    elif key == 'down':
                        current = (current + 1) % len(_MENU_LABELS)
                    elif key == 'enter':
                        break
                    elif key == 'q':
                        current = len(_MENU_LABELS) - 1  # jump to Exit
                        break
                    elif key == 'escape':
                        continue  # already at top-level menu — no-op
                    else:
                        continue

                    cursor_up(_MENU_TOTAL_LINES)
                    _render_menu(current)
            finally:
                show_cursor()

            if current == 3:  # Exit
                console.print()
                console.print(
                    Panel(
                        f"[{TEXT_SECONDARY}]Goodbye. Run [bold {TEXT_PRIMARY}]sift[/bold {TEXT_PRIMARY}] "
                        f"anytime to return.[/{TEXT_SECONDARY}]",
                        border_style=TEXT_MUTED,
                    )
                )
                console.print()
                break

            elif current == 0:
                _interactive_analyze()

            elif current == 1:
                _interactive_scrape()

            elif current == 2:
                console.clear()
                print_large_banner()
                run_setup_wizard()
                load_dotenv(override=True)
                # The wizard itself prints a save/discard confirmation Panel;
                # pause briefly so the user can read it before we redraw the
                # main menu.
                time.sleep(1.2)
    finally:
        # Belt-and-suspenders: ensure cursor is visible if we exit unexpectedly.
        show_cursor()


# ---------------------------------------------------------------------------
# Interactive action handlers
# ---------------------------------------------------------------------------


def _print_returning() -> None:
    """Print a brief 'returning to menu' status and pause for readability."""
    console.print()
    console.print(f"  [{AMBER}]Returning to menu.[/{AMBER}]")
    time.sleep(1.2)


def _interactive_analyze() -> None:
    """Prompt for product and sources, then run the full analyze pipeline."""
    console.clear()
    print_large_banner()

    _render_sub_header(
        "Analyze Product",
        "Sift will scrape feedback, cluster complaints, "
        "and generate AI-powered insights.",
    )
    console.print()

    product_raw = read_line_with_escape(
        f"  [bold {TEXT_PRIMARY}]Product name(s)[/bold {TEXT_PRIMARY}] "
        f"[{TEXT_MUTED}](comma-separated, Esc to cancel)[/{TEXT_MUTED}]",
    )
    if product_raw is None:
        _print_returning()
        return

    products = [p.strip() for p in product_raw.split(",") if p.strip()]
    if not products:
        console.print(
            f"[{AMBER}]No product entered. Returning to menu.[/{AMBER}]"
        )
        time.sleep(1.2)
        return

    sources = _prompt_sources()
    if not sources:
        console.print(
            f"[{AMBER}]No sources available. Returning to menu.[/{AMBER}]"
        )
        time.sleep(1.2)
        return

    output_dir = read_line_with_escape(
        f"  [bold {TEXT_PRIMARY}]Output directory[/bold {TEXT_PRIMARY}]",
        default="output",
    )
    if output_dir is None:
        _print_returning()
        return

    settings = load_settings()
    verbose = confirm_with_escape(
        f"  [bold {TEXT_PRIMARY}]Enable verbose logging?[/bold {TEXT_PRIMARY}]",
        default=False,
    )
    if verbose is None:
        _print_returning()
        return

    # Lazy import to avoid circular dependency at module level.
    from sift.cli import run_analyze as _run

    _run(
        products=products,
        sources=sources,
        settings=settings,
        output=output_dir,
        no_preview=False,
        verbose=verbose,
        show_banner=False,
    )

    console.print()
    Prompt.ask(
        f"  [{TEXT_MUTED}]Press Enter to return to the menu[/{TEXT_MUTED}]",
        default="",
        show_default=False,
    )


def _interactive_scrape() -> None:
    """Prompt for product and sources, then run the scrape-only pipeline."""
    console.clear()
    print_large_banner()

    _render_sub_header(
        "Scrape Product",
        "Collect raw feedback without clustering or analysis.",
    )
    console.print()

    product_name = read_line_with_escape(
        f"  [bold {TEXT_PRIMARY}]Product name[/bold {TEXT_PRIMARY}] "
        f"[{TEXT_MUTED}](Esc to cancel)[/{TEXT_MUTED}]",
    )
    if product_name is None:
        _print_returning()
        return

    if not product_name.strip():
        console.print(
            f"[{AMBER}]No product entered. Returning to menu.[/{AMBER}]"
        )
        time.sleep(1.2)
        return

    sources = _prompt_sources()
    if not sources:
        console.print(
            f"[{AMBER}]No sources available. Returning to menu.[/{AMBER}]"
        )
        time.sleep(1.2)
        return

    output_dir = read_line_with_escape(
        f"  [bold {TEXT_PRIMARY}]Output directory[/bold {TEXT_PRIMARY}]",
        default="output",
    )
    if output_dir is None:
        _print_returning()
        return

    settings = load_settings()
    verbose = confirm_with_escape(
        f"  [bold {TEXT_PRIMARY}]Enable verbose logging?[/bold {TEXT_PRIMARY}]",
        default=False,
    )
    if verbose is None:
        _print_returning()
        return

    from sift.cli import run_scrape as _run

    _run(
        product=product_name.strip(),
        sources=sources,
        settings=settings,
        output=output_dir,
        verbose=verbose,
        show_banner=False,
    )

    console.print()
    Prompt.ask(
        f"  [{TEXT_MUTED}]Press Enter to return to the menu[/{TEXT_MUTED}]",
        default="",
        show_default=False,
    )


def _prompt_sources() -> list[str]:
    """Ask the user which sources to use. Returns a list of source keys.

    Returns empty list if the user presses Escape at any point.
    """
    settings = load_settings()
    defaults = default_sources(settings)
    use_defaults = confirm_with_escape(
        f"  [bold {TEXT_PRIMARY}]Use default sources?[/bold {TEXT_PRIMARY}] "
        f"[{TEXT_MUTED}]({', '.join(defaults[:6])}{'...' if len(defaults) > 6 else ''})[/{TEXT_MUTED}]",
        default=True,
    )
    if use_defaults is None:
        return []
    if use_defaults:
        return defaults

    console.print()
    console.print(f"  [bold {TEXT_PRIMARY}]Available sources:[/bold {TEXT_PRIMARY}]")
    selected: list[str] = []
    for i, src in enumerate(sorted(AVAILABLE_SOURCES), 1):
        default_yes = src in defaults
        label = f"  [{i:>2}] {src}"
        if default_yes:
            label += f" [{TEXT_MUTED}](default)[/{TEXT_MUTED}]"
        result = confirm_with_escape(label, default=default_yes)
        if result is None:
            return []
        if result:
            selected.append(src)

    return selected
