"""Shared ceremonies for Sift's interactive wizards.

Both ``sift.ui.setup`` (API-key wizard) and ``sift.ui.config_wizard``
(config.yaml editor) follow the same script: print a welcome panel,
walk a list of entries grouped by section, on ``Esc`` pop a
Save / Discard / Cancel popup, then write to disk and print a
success panel. The presentation pieces of that script live here so
each wizard only has to own its entry list, parsing logic, and save
implementation.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from sift.ui._terminal import (
    clear_lines,
    console,
    cursor_up,
    hide_cursor,
    read_key,
    show_cursor,
)
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


# ── Save / Discard / Cancel popup ──────────────────────────────────────


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
    hide_cursor()
    try:
        while True:
            key = read_key()
            if key == 'up':
                current = (current - 1) % len(_EXIT_CHOICES)
            elif key == 'down':
                current = (current + 1) % len(_EXIT_CHOICES)
            elif key == 'enter':
                clear_lines(rendered_lines)
                return _EXIT_CHOICES[current][0]
            elif key == 'escape':
                clear_lines(rendered_lines)
                return "cancel"
            else:
                continue
            cursor_up(rendered_lines)
            render()
    finally:
        show_cursor()


# ── Shared wizard panels ───────────────────────────────────────────────


def print_welcome_panel(message: str) -> None:
    """Print the violet-bordered welcome panel both wizards open with."""
    console.print()
    console.print(
        Panel.fit(
            Text(message, style=f"bold {TEXT_PRIMARY}"),
            border_style=VIOLET,
        )
    )
    console.print()


def print_section_rule(title: str, color: str = VIOLET) -> None:
    """Print a left-aligned ``Rule`` separator with the given title."""
    console.print(
        Rule(f"[bold {color}]{title}[/bold {color}]", style=TEXT_MUTED, align="left")
    )
    console.print()


def print_discarded_panel(target_label: str) -> None:
    """Print the amber ``Changes discarded`` panel.

    ``target_label`` describes what was *not* modified (e.g. ``.env`` or
    ``config.yaml``).
    """
    console.print()
    console.print(
        Panel(
            f"[bold {AMBER}]{ICON_DOT} Changes discarded.[/bold {AMBER}]\n"
            f"[{TEXT_SECONDARY}]Your {target_label} was not modified.[/{TEXT_SECONDARY}]",
            border_style=AMBER,
        )
    )
    console.print()


def print_saved_panel(message_lines: list[str]) -> None:
    """Print the emerald success panel. Each entry in ``message_lines`` is one row."""
    from sift.ui.theme import EMERALD, ICON_DONE

    body = "\n".join(
        f"[bold {EMERALD}]{ICON_DONE} {line}[/bold {EMERALD}]"
        for line in message_lines
    )
    console.print(Panel(body, border_style=EMERALD))
    console.print()
