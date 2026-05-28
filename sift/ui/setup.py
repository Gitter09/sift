"""First-run setup wizard for Sift API keys.

Detects whether the required API keys are configured and walks the user
through interactive prompts if they aren't. Writes keys to a local .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, dotenv_values
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from sift.config_defaults import generate_default_config
from sift.ui.theme import (
    AMBER,
    EMERALD,
    ICON_DONE,
    ICON_DOT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    VIOLET,
)
console = Console()

# Absolute path to the .env file in the project root (or cwd).
_ENV_PATH = Path(os.getenv("SIFT_ENV_PATH", Path.cwd() / ".env"))

# Required: the LLM key is mandatory for analysis to work.
_REQUIRED_KEY = "LLM_API_KEY"

_EXISTING_SENTINEL = "(existing — press Enter to keep)"

# All keys the setup wizard knows about, with their prompt labels and defaults.
_KEYS = [
    {
        "key": "LLM_API_KEY",
        "label": "LLM API Key",
        "default": "",
        "password": True,
        "required": True,
    },
    {
        "key": "LLM_BASE_URL",
        "label": "LLM Base URL",
        "default": "https://api.openai.com/v1",
        "password": False,
        "required": False,
    },
    {
        "key": "LLM_MODEL",
        "label": "LLM Model",
        "default": "gpt-4o-mini",
        "password": False,
        "required": False,
    },
]

_OPTIONAL_KEYS = [
    {
        "key": "YOUTUBE_API_KEY",
        "label": "YouTube API Key",
        "default": "",
        "password": True,
    },
    {
        "key": "GITHUB_TOKEN",
        "label": "GitHub Token",
        "default": "",
        "password": True,
    },
    {
        "key": "REDDIT_CLIENT_ID",
        "label": "Reddit Client ID",
        "default": "",
        "password": False,
    },
    {
        "key": "REDDIT_CLIENT_SECRET",
        "label": "Reddit Client Secret",
        "default": "",
        "password": True,
    },
    {
        "key": "PRODUCT_HUNT_CLIENT_ID",
        "label": "Product Hunt Client ID (API Key)",
        "default": "",
        "password": False,
    },
    {
        "key": "PRODUCT_HUNT_CLIENT_SECRET",
        "label": "Product Hunt Client Secret (API Secret)",
        "default": "",
        "password": True,
    },
    {
        "key": "BRAVE_SEARCH_API_KEY",
        "label": "Brave Search API Key (api.search.brave.com — free tier 2k/mo)",
        "default": "",
        "password": True,
    },
]


def is_configured() -> bool:
    """Return True if the required API key is present in the .env file."""
    load_dotenv(_ENV_PATH)
    value = os.getenv(_REQUIRED_KEY, "").strip()
    return bool(value)


def _print_welcome() -> None:
    console.print()
    console.print(
        Panel.fit(
            Text(
                "Welcome to Sift. Let's configure your API keys.\n"
                "Press Enter to accept defaults. Press Esc anytime to save or discard and exit.",
                style=f"bold {TEXT_PRIMARY}",
            ),
            border_style=VIOLET,
        )
    )
    console.print()


def _section_rule(title: str, color: str) -> None:
    console.print(Rule(f"[bold {color}]{title}[/bold {color}]", style=TEXT_MUTED, align="left"))
    console.print()


def _ask_entry(entry: dict, existing: dict[str, Optional[str]], required_section: bool) -> Optional[str]:
    """Prompt for a single key. Returns the user's value, or ``None`` if Esc."""
    from sift.ui.menu import read_line_with_escape  # lazy: avoid circular import
    key = entry["key"]
    default = existing.get(key) or entry["default"]
    is_password = entry.get("password", False)

    if is_password and default:
        # For already-set secrets, show a placeholder default; we'll swap it
        # back to the real value if the user presses Enter without typing.
        shown_default = _EXISTING_SENTINEL
    else:
        shown_default = default

    if required_section:
        label = f"  [bold {TEXT_PRIMARY}]{entry['label']}[/bold {TEXT_PRIMARY}]"
    else:
        label = f"  [{TEXT_SECONDARY}]{entry['label']}[/{TEXT_SECONDARY}]"

    value = read_line_with_escape(
        label,
        default=shown_default,
        password=is_password,
        show_default=bool(shown_default),
    )
    if value is None:
        return None
    if is_password and default and value == _EXISTING_SENTINEL:
        value = default
    return value.strip()


def _build_entries() -> list[tuple[str, dict]]:
    """Flatten the prompt list with section markers for resumable iteration."""
    out: list[tuple[str, dict]] = []
    for e in _KEYS:
        out.append(("required", e))
    for e in _OPTIONAL_KEYS:
        out.append(("optional", e))
    return out


def run_setup_wizard() -> None:
    """Walk the user through interactive API key configuration and save to .env.

    Esc at any prompt opens a Save/Discard/Cancel dialog.
    """
    existing: dict[str, Optional[str]] = {}
    if _ENV_PATH.exists():
        existing = dict(dotenv_values(_ENV_PATH))

    _print_welcome()

    new_values: dict[str, str] = {}
    entries = _build_entries()

    i = 0
    last_section: Optional[str] = None
    while i < len(entries):
        section, entry = entries[i]
        if section != last_section:
            if section == "required":
                _section_rule("REQUIRED", VIOLET)
            else:
                console.print()
                _section_rule("OPTIONAL", TEXT_SECONDARY)
            last_section = section

        value = _ask_entry(entry, existing, required_section=(section == "required"))

        if value is None:
            # Esc pressed — ask what to do.
            from sift.ui.menu import prompt_exit_choice  # lazy: avoid circular import
            choice = prompt_exit_choice()
            if choice == "save":
                console.print()
                _save_env(new_values, existing)
                return
            if choice == "discard":
                console.print()
                console.print(
                    Panel(
                        f"[bold {AMBER}]{ICON_DOT} Changes discarded.[/bold {AMBER}]\n"
                        f"[{TEXT_SECONDARY}]Your .env was not modified.[/{TEXT_SECONDARY}]",
                        border_style=AMBER,
                    )
                )
                console.print()
                return
            # Cancel — re-render section header for context, then re-prompt
            # this same entry.
            console.print()
            if section == "required":
                _section_rule("REQUIRED", VIOLET)
            else:
                _section_rule("OPTIONAL", TEXT_SECONDARY)
            last_section = section
            continue

        if value or entry.get("required"):
            new_values[entry["key"]] = value

        i += 1

    console.print()
    _save_env(new_values, existing)


def _save_env(new_values: dict[str, str], existing: dict[str, Optional[str]]) -> None:
    """Write the updated key-value pairs to the .env file.

    Preserves any lines in the existing .env that aren't among our known keys,
    so user customizations (G2_REQUEST_DELAY, MAX_FEEDBACK_PER_SOURCE, etc.)
    are not lost.
    """
    merged = {k: v for k, v in existing.items() if v is not None}
    merged.update(new_values)

    managed_keys = {e["key"] for e in _KEYS} | {e["key"] for e in _OPTIONAL_KEYS}

    lines: list[str] = []
    seen_managed = set()

    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    lines.append(line.rstrip("\n"))
                    continue

                raw_key = stripped.split("=", 1)[0].strip()
                if raw_key in managed_keys:
                    if raw_key not in seen_managed:
                        lines.append(f"{raw_key}={merged.get(raw_key, '')}")
                        seen_managed.add(raw_key)
                else:
                    lines.append(line.rstrip("\n"))

    for key in merged:
        if key in managed_keys and key not in seen_managed:
            lines.append(f"{key}={merged[key]}")
            seen_managed.add(key)

    with open(_ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Also generate a default config.yaml if one doesn't exist yet.
    _CONFIG_PATH = os.getenv("SIFT_CONFIG_PATH", "config.yaml")
    created_config = generate_default_config(_CONFIG_PATH)

    if created_config:
        console.print(
            Panel(
                f"[bold {EMERALD}]{ICON_DONE} Configuration saved to {_ENV_PATH}[/bold {EMERALD}]\n"
                f"[bold {EMERALD}]{ICON_DONE} Default config.yaml created at {_CONFIG_PATH}[/bold {EMERALD}]",
                border_style=EMERALD,
            )
        )
    else:
        console.print(
            Panel(
                f"[bold {EMERALD}]{ICON_DONE} Configuration saved to {_ENV_PATH}[/bold {EMERALD}]",
                border_style=EMERALD,
            )
        )
    console.print()
