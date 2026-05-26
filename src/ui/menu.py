"""Interactive main menu for Sift.

Shown when ``sift`` is run with no subcommand. Provides an arrow-key
navigable menu to launch analysis, scraping, or reconfigure API keys.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import tty

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from src.ui.display import print_large_banner
from src.ui.setup import run_setup_wizard
from src.config import load_settings
from src.scrapers.factory import AVAILABLE_SOURCES, default_sources

console = Console()

_MENU_LABELS = [
    "Analyze a product",
    "Scrape a product (no analysis)",
    "Settings & API keys",
    "Exit",
]

# Lines printed by _render_menu(): border×2 + padding×2 + items + hint
_MENU_TOTAL_LINES = len(_MENU_LABELS) + 4 + 1


def _read_key() -> str:
    """Read one keypress from stdin in raw mode; recognizes arrow keys."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)
        if ch == b'\x1b':
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if ready:
                ch2 = os.read(fd, 1)
                if ch2 == b'[':
                    ready2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready2:
                        ch3 = os.read(fd, 1)
                        if ch3 == b'A':
                            return 'up'
                        if ch3 == b'B':
                            return 'down'
            return 'escape'
        if ch in (b'\r', b'\n'):
            return 'enter'
        if ch == b'\x03':
            raise KeyboardInterrupt
        return ch.decode('utf-8', errors='replace')
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _render_menu(current: int) -> None:
    lines = []
    for i, label in enumerate(_MENU_LABELS):
        if i == current:
            lines.append(f"   [bold]▶  {label}[/bold]")
        else:
            lines.append(f"      {label}")
    console.print(Panel("\n".join(lines), title="Main Menu", border_style="white", padding=(1, 2)))
    console.print("  [dim]↑ ↓  navigate    enter  select    q  quit[/dim]")


def run_main_menu() -> None:
    """Main interactive loop: show banner, navigate menu with arrow keys."""
    current = 0

    while True:
        console.clear()
        print_large_banner()
        _render_menu(current)

        # Navigate until Enter or q
        while True:
            key = _read_key()
            if key == 'up':
                current = (current - 1) % len(_MENU_LABELS)
            elif key == 'down':
                current = (current + 1) % len(_MENU_LABELS)
            elif key == 'enter':
                break
            elif key == 'q':
                current = len(_MENU_LABELS) - 1  # jump to Exit
                break
            else:
                continue

            sys.stdout.write(f'\033[{_MENU_TOTAL_LINES}A\r')
            sys.stdout.flush()
            _render_menu(current)

        if current == 3:  # Exit
            console.print()
            console.print(
                Panel(
                    "[dim]Goodbye! Run [bold]sift[/bold] anytime to return.[/dim]",
                    border_style="dim",
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
            console.print(
                Panel(
                    "[green bold]✓ Settings updated.[/green bold]\n"
                    "[dim]Press Enter to return to the menu.[/dim]",
                    border_style="green",
                )
            )
            Prompt.ask("", default="", show_default=False)


# ---------------------------------------------------------------------------
# Interactive action handlers
# ---------------------------------------------------------------------------


def _interactive_analyze() -> None:
    """Prompt for product and sources, then run the full analyze pipeline."""
    console.clear()
    print_large_banner()

    console.print(
        Panel(
            "[bold]Analyze Product[/bold]\n"
            "[dim]Sift will scrape feedback, cluster complaints, "
            "and generate AI-powered insights.[/dim]",
            border_style="white",
        )
    )
    console.print()

    product_raw = Prompt.ask(
        "  [bold]Product name(s)[/bold] [dim](comma-separated)[/dim]"
    )
    products = [p.strip() for p in product_raw.split(",") if p.strip()]
    if not products:
        console.print("[yellow]No product entered. Returning to menu.[/yellow]")
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    sources = _prompt_sources()
    if not sources:
        console.print("[yellow]No sources available. Returning to menu.[/yellow]")
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    output_dir = Prompt.ask(
        "  [bold]Output directory[/bold]",
        default="output",
    )

    settings = load_settings()
    verbose = Confirm.ask("  [bold]Enable verbose logging?[/bold]", default=False)

    # Lazy import to avoid circular dependency at module level.
    from src.cli import run_analyze as _run

    _run(
        products=products,
        sources=sources,
        settings=settings,
        output=output_dir,
        no_preview=False,
        verbose=verbose,
    )

    console.print()
    Prompt.ask(
        "  [dim]Press Enter to return to the menu[/dim]",
        default="",
        show_default=False,
    )


def _interactive_scrape() -> None:
    """Prompt for product and sources, then run the scrape-only pipeline."""
    console.clear()
    print_large_banner()

    console.print(
        Panel(
            "[bold]Scrape Product[/bold]\n"
            "[dim]Collect raw feedback without clustering or analysis.[/dim]",
            border_style="white",
        )
    )
    console.print()

    product = Prompt.ask("  [bold]Product name[/bold]")
    if not product.strip():
        console.print("[yellow]No product entered. Returning to menu.[/yellow]")
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    sources = _prompt_sources()
    if not sources:
        console.print("[yellow]No sources available. Returning to menu.[/yellow]")
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    output_dir = Prompt.ask(
        "  [bold]Output directory[/bold]",
        default="output",
    )

    settings = load_settings()
    verbose = Confirm.ask("  [bold]Enable verbose logging?[/bold]", default=False)

    from src.cli import run_scrape as _run

    _run(
        product=product.strip(),
        sources=sources,
        settings=settings,
        output=output_dir,
        verbose=verbose,
    )

    console.print()
    Prompt.ask(
        "  [dim]Press Enter to return to the menu[/dim]",
        default="",
        show_default=False,
    )


def _prompt_sources() -> list[str]:
    """Ask the user which sources to use. Returns a list of source keys."""
    settings = load_settings()
    defaults = default_sources(settings)
    use_defaults = Confirm.ask(
        f"  [bold]Use default sources?[/bold] [dim]({', '.join(defaults[:6])}{'...' if len(defaults) > 6 else ''})[/dim]",
        default=True,
    )
    if use_defaults:
        return defaults

    console.print()
    console.print("  [bold]Available sources:[/bold]")
    selected: list[str] = []
    for i, src in enumerate(sorted(AVAILABLE_SOURCES), 1):
        default_yes = src in defaults
        label = f"  [{i:>2}] {src}"
        if default_yes:
            label += " [dim](default)[/dim]"
        if Confirm.ask(label, default=default_yes):
            selected.append(src)

    return selected
