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
from rich.prompt import Prompt, Confirm
from rich.text import Text

console = Console()

# Absolute path to the .env file in the project root (or cwd).
_ENV_PATH = Path(os.getenv("SIFT_ENV_PATH", Path.cwd() / ".env"))

# Required: the LLM key is mandatory for analysis to work.
_REQUIRED_KEY = "LLM_API_KEY"

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
]


def is_configured() -> bool:
    """Return True if the required API key is present in the .env file.

    Loads dotenv so os.getenv picks up values from the file, then checks for
    the required key.
    """
    load_dotenv(_ENV_PATH)
    value = os.getenv(_REQUIRED_KEY, "").strip()
    return bool(value)


def run_setup_wizard() -> None:
    """Walk the user through interactive API key configuration and save to .env.

    Pre-fills prompts with existing values so re-running the wizard doesn't
    force the user to re-type everything.
    """
    # Load existing values from .env (if any) for pre-filling.
    existing: dict[str, Optional[str]] = {}
    if _ENV_PATH.exists():
        existing = dict(dotenv_values(_ENV_PATH))

    console.print()
    console.print(
        Panel.fit(
            Text(
                "Welcome to Sift! Let's configure your API keys.\n"
                "Press Enter to accept defaults or leave optional fields empty.",
                style="bold",
            ),
            border_style="white",
        )
    )
    console.print()

    new_values: dict[str, str] = {}

    # --- Required keys ---
    console.print(
        Panel("[bold]Required[/bold]", border_style="yellow", padding=(0, 1))
    )
    console.print()
    for entry in _KEYS:
        key = entry["key"]
        default = existing.get(key) or entry["default"]
        prompt_kwargs = {
            "default": default,
            "show_default": bool(default),
        }
        if entry["password"] and not default:
            prompt_kwargs["password"] = True
        elif entry["password"] and default:
            # When there's an existing value, show it masked as placeholder
            prompt_kwargs["default"] = "(existing — press Enter to keep)"
            prompt_kwargs["show_default"] = True
            prompt_kwargs["password"] = True

        value = Prompt.ask(f"  [bold]{entry['label']}[/bold]", **prompt_kwargs)

        # If user accepted "(existing — press Enter to keep)", use the real value.
        if entry["password"] and default and value == "(existing — press Enter to keep)":
            value = default

        if value.strip() or entry["required"]:
            new_values[key] = value.strip()

    console.print()

    # --- Optional keys ---
    console.print(
        Panel("[bold]Optional[/bold]", border_style="dim", padding=(0, 1))
    )
    console.print()
    for entry in _OPTIONAL_KEYS:
        key = entry["key"]
        default = existing.get(key) or entry["default"]
        prompt_kwargs = {
            "default": default if default else "",
            "show_default": bool(default),
        }
        if entry["password"] and not default:
            prompt_kwargs["password"] = True
        elif entry["password"] and default:
            prompt_kwargs["default"] = "(existing — press Enter to keep)"
            prompt_kwargs["show_default"] = True
            prompt_kwargs["password"] = True

        value = Prompt.ask(f"  [dim]{entry['label']}[/dim]", **prompt_kwargs)

        if entry["password"] and default and value == "(existing — press Enter to keep)":
            value = default

        if value.strip():
            new_values[key] = value.strip()

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

    # Determine the set of keys we manage (required + optional).
    managed_keys = {e["key"] for e in _KEYS} | {e["key"] for e in _OPTIONAL_KEYS}

    lines: list[str] = []
    seen_managed = set()

    # Preserve existing lines, updating managed keys in-place.
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
                    # Skip duplicate or old entries for this key.
                else:
                    lines.append(line.rstrip("\n"))

    # Append any managed keys not yet written.
    for key in merged:
        if key in managed_keys and key not in seen_managed:
            lines.append(f"{key}={merged[key]}")
            seen_managed.add(key)

    with open(_ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    console.print(
        Panel(
            f"[green bold]\u2713 Configuration saved to {_ENV_PATH}[/green bold]",
            border_style="green",
        )
    )
    console.print()
