"""Low-level terminal I/O for Sift's interactive UI.

This module is a *leaf* — it has no internal imports beyond
``sift.ui.theme`` for color constants. Both ``sift.ui.menu`` and the
two wizards (``sift.ui.setup``, ``sift.ui.config_wizard``) import
from here, which is how the previous lazy-import circular-dependency
workaround was retired.

Contents:

  - ``read_key()`` — raw single-key reader that recognizes the arrow
    keys, Enter, Escape, and Ctrl-C.
  - ``read_line_with_escape(...)`` — line editor that returns ``None``
    if the user presses Escape; supports password masking and a
    rendered default hint.
  - ``confirm_with_escape(...)`` — Y/N prompt that returns
    ``True``/``False``/``None`` (None on Escape).
  - Cursor helpers (``hide_cursor``, ``show_cursor``, ``clear_lines``,
    ``cursor_up``) that wrap the ANSI escape sequences scattered
    inline throughout ``menu.py``.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import tty

from rich.console import Console

from sift.ui.theme import TEXT_MUTED

console = Console()


# ── Cursor / screen helpers ────────────────────────────────────────────


def hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def clear_lines(n: int) -> None:
    """Move the cursor up ``n`` lines, return to column 0, and clear below."""
    sys.stdout.write(f"\033[{n}A\r\033[J")
    sys.stdout.flush()


def cursor_up(n: int) -> None:
    """Move the cursor up ``n`` lines and return to column 0 (no clear)."""
    sys.stdout.write(f"\033[{n}A\r")
    sys.stdout.flush()


# ── Key / line / confirm readers ───────────────────────────────────────


def read_key() -> str:
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
                    _ = os.read(fd, 1)
                    ready2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready2:
                        _ = os.read(fd, 1)
                    continue
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


def confirm_with_escape(
    label: str,
    default: bool = True,
) -> bool | None:
    """Render a Rich-styled Yes/No confirm and return True/False, or None if Esc.

    Mirrors ``rich.prompt.Confirm.ask`` but intercepts Esc to cancel back
    to the main menu.

    - ``default`` controls the capital letter: ``Y/n`` when True, ``y/N``
      when False.
    - Returns ``None`` when the user presses Escape.
    """
    yes_char = "Y" if default else "y"
    no_char = "n" if default else "N"
    suffix = f" [{TEXT_MUTED}]({yes_char}/{no_char})[/{TEXT_MUTED}]"
    console.print(f"{label}{suffix}[{TEXT_MUTED}]:[/{TEXT_MUTED}] ", end="")
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1)
            if ch == b'\x1b':
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready:
                    _ = os.read(fd, 1)
                    ready2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready2:
                        _ = os.read(fd, 1)
                    continue
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return None
            if ch in (b'\r', b'\n'):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return default
            if ch == b'\x03':
                raise KeyboardInterrupt
            if ch.lower() == b'y':
                sys.stdout.write("y\r\n")
                sys.stdout.flush()
                return True
            if ch.lower() == b'n':
                sys.stdout.write("n\r\n")
                sys.stdout.flush()
                return False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
