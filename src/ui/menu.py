"""Interactive main menu for Sift.

Shown when ``sift`` is run with no subcommand. Provides an arrow-key
navigable menu to launch analysis, scraping, or reconfigure API keys.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from src.ui.display import print_large_banner, VERSION, _git_info
from src.ui.theme import (
    ACCENT_COLOR,
    AMBER,
    CYAN,
    EMERALD,
    ICON_DONE,
    ICON_DOT,
    ICON_SELECT,
    ROSE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    VIOLET,
)
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

# Lines printed by _render_menu(): borderx2 + paddingx2 + items + hint
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


def read_line_with_escape(
    label: str,
    default: str = "",
    password: bool = False,
    show_default: bool = True,
) -> str | None:
    """Render a Rich-styled prompt and read a line, returning None if Esc pressed.

    Behaves like ``rich.prompt.Prompt.ask`` for the common case but intercepts
    the Escape key and returns ``None`` so callers can offer a save/discard/
    cancel dialog.

    - ``default`` is returned when the user presses Enter on an empty buffer.
    - ``password`` echoes ``*`` instead of the typed character.
    - Backspace and Ctrl-C are handled; arrow-key escape sequences are
      consumed so they don't accidentally trigger Esc-exit.
    """
    # Render the label (Rich markup ok) plus a default hint, mirroring
    # Prompt.ask's visual style.
    suffix = ""
    if show_default and default:
        suffix = f" [{TEXT_MUTED}]({default})[/{TEXT_MUTED}]"
    console.print(f"{label}{suffix}[{TEXT_MUTED}]:[/{TEXT_MUTED}] ", end="")
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf: list[str] = []
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1)
            if ch == b'\x1b':
                # Disambiguate bare Esc from arrow / function key sequences.
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready:
                    # Consume the rest of the escape sequence and ignore.
                    _ = os.read(fd, 1)
                    ready2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready2:
                        _ = os.read(fd, 1)
                    continue
                # Bare Esc — cancel.
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return None
            if ch in (b'\r', b'\n'):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                value = "".join(buf)
                return value if value else default
            if ch == b'\x03':
                raise KeyboardInterrupt
            if ch in (b'\x7f', b'\x08'):
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            try:
                decoded = ch.decode('utf-8')
            except UnicodeDecodeError:
                continue
            if not decoded.isprintable():
                continue
            buf.append(decoded)
            sys.stdout.write("*" if password else decoded)
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


_EXIT_CHOICES = [
    ("save", "Save", "Persist what you've entered so far"),
    ("discard", "Discard", "Throw away changes and return to menu"),
    ("cancel", "Cancel", "Continue editing"),
]


def prompt_exit_choice() -> str:
    """Render a Save/Discard/Cancel popup and return one of the choice keys.

    Defaults the selection to **Cancel** so an accidental Enter is safe.
    """
    current = 2  # Cancel
    rendered_lines = len(_EXIT_CHOICES) + 4 + 1  # panel borders + padding + hint

    def render() -> None:
        lines = []
        for i, (_, label, desc) in enumerate(_EXIT_CHOICES):
            if i == current:
                lines.append(
                    f"   [bold {CYAN}]{ICON_SELECT}  {label}[/bold {CYAN}]  "
                    f"[{TEXT_MUTED}]{desc}[/{TEXT_MUTED}]"
                )
            else:
                lines.append(
                    f"      {label}  [{TEXT_MUTED}]{desc}[/{TEXT_MUTED}]"
                )
        console.print(
            Panel(
                "\n".join(lines),
                title=f"[{AMBER}]Unsaved changes[/{AMBER}]",
                title_align="center",
                border_style=AMBER,
                padding=(1, 2),
            )
        )
        console.print(
            f"  [{VIOLET}]↑ ↓[/{VIOLET}]  "
            f"[{TEXT_MUTED}]navigate[/{TEXT_MUTED}]  {ICON_DOT}  "
            f"enter  [{TEXT_SECONDARY}]select[/{TEXT_SECONDARY}]"
        )

    render()
    sys.stdout.write('\033[?25l')
    sys.stdout.flush()
    try:
        while True:
            key = _read_key()
            if key == 'up':
                current = (current - 1) % len(_EXIT_CHOICES)
            elif key == 'down':
                current = (current + 1) % len(_EXIT_CHOICES)
            elif key == 'enter':
                return _EXIT_CHOICES[current][0]
            elif key == 'escape':
                return "cancel"
            else:
                continue
            sys.stdout.write(f'\033[{rendered_lines}A\r')
            sys.stdout.flush()
            render()
    finally:
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()


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
        f"q  [{TEXT_MUTED}]quit[/{TEXT_MUTED}]"
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
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
            try:
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
            finally:
                sys.stdout.write('\033[?25h')
                sys.stdout.flush()

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
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Interactive action handlers
# ---------------------------------------------------------------------------


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

    product_raw = Prompt.ask(
        f"  [bold {TEXT_PRIMARY}]Product name(s)[/bold {TEXT_PRIMARY}] "
        f"[{TEXT_MUTED}](comma-separated)[/{TEXT_MUTED}]"
    )
    products = [p.strip() for p in product_raw.split(",") if p.strip()]
    if not products:
        console.print(
            f"[{AMBER}]No product entered. Returning to menu.[/{AMBER}]"
        )
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    sources = _prompt_sources()
    if not sources:
        console.print(
            f"[{AMBER}]No sources available. Returning to menu.[/{AMBER}]"
        )
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    output_dir = Prompt.ask(
        f"  [bold {TEXT_PRIMARY}]Output directory[/bold {TEXT_PRIMARY}]",
        default="output",
    )

    settings = load_settings()
    verbose = Confirm.ask(
        f"  [bold {TEXT_PRIMARY}]Enable verbose logging?[/bold {TEXT_PRIMARY}]",
        default=False,
    )

    # Lazy import to avoid circular dependency at module level.
    from src.cli import run_analyze as _run

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

    product = Prompt.ask(f"  [bold {TEXT_PRIMARY}]Product name[/bold {TEXT_PRIMARY}]")
    if not product.strip():
        console.print(
            f"[{AMBER}]No product entered. Returning to menu.[/{AMBER}]"
        )
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    sources = _prompt_sources()
    if not sources:
        console.print(
            f"[{AMBER}]No sources available. Returning to menu.[/{AMBER}]"
        )
        Prompt.ask("  Press Enter to continue", default="", show_default=False)
        return

    output_dir = Prompt.ask(
        f"  [bold {TEXT_PRIMARY}]Output directory[/bold {TEXT_PRIMARY}]",
        default="output",
    )

    settings = load_settings()
    verbose = Confirm.ask(
        f"  [bold {TEXT_PRIMARY}]Enable verbose logging?[/bold {TEXT_PRIMARY}]",
        default=False,
    )

    from src.cli import run_scrape as _run

    _run(
        product=product.strip(),
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
    """Ask the user which sources to use. Returns a list of source keys."""
    settings = load_settings()
    defaults = default_sources(settings)
    use_defaults = Confirm.ask(
        f"  [bold {TEXT_PRIMARY}]Use default sources?[/bold {TEXT_PRIMARY}] "
        f"[{TEXT_MUTED}]({', '.join(defaults[:6])}{'...' if len(defaults) > 6 else ''})[/{TEXT_MUTED}]",
        default=True,
    )
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
        if Confirm.ask(label, default=default_yes):
            selected.append(src)

    return selected
