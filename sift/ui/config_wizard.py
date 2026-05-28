"""Interactive wizard for editing config.yaml.

Walks the user through every meaningful field, using current values
(if config.yaml exists) as defaults. Esc opens a Save / Discard / Cancel
panel that mirrors the API key setup wizard.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import yaml
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from sift.config_defaults import DEFAULT_CONFIG
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
from sift.ui.setup import console  # reuse the shared Rich console


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Each entry: (section_title, path_tuple, label, kind)
# Sections are rendered in order; section title changes draw a new rule.
_ENTRIES: list[tuple[str, tuple[str, ...], str, str]] = [
    # SOURCES
    ("SOURCES", ("sources", "default_sources"), "Default sources", "list_str"),
    ("SOURCES", ("sources", "disabled_sources"), "Disabled sources", "list_str"),
    # RELEVANCE
    ("RELEVANCE", ("relevance", "enabled"), "Enabled", "bool"),
    ("RELEVANCE", ("relevance", "threshold"), "Threshold", "float"),
    ("RELEVANCE", ("relevance", "min_items_before_relaxing"), "Min items before relaxing", "int"),
    # REDDIT
    ("REDDIT", ("reddit", "subreddits"), "Subreddits", "list_str"),
    ("REDDIT", ("reddit", "search_sort"), "Search sort", "str"),
    ("REDDIT", ("reddit", "max_posts"), "Max posts", "int"),
    ("REDDIT", ("reddit", "max_comments_per_post"), "Max comments per post", "int"),
    ("REDDIT", ("reddit", "target_rate_per_minute"), "Target rate per minute", "int"),
    ("REDDIT", ("reddit", "praw_ratelimit_seconds"), "PRAW ratelimit seconds", "int"),
    ("REDDIT", ("reddit", "subreddit_delay"), "Subreddit delay (s)", "float"),
    # G2
    ("G2", ("g2", "request_delay"), "Request delay (s)", "float"),
    ("G2", ("g2", "max_pages"), "Max pages", "int"),
    ("G2", ("g2", "user_agent_rotation"), "User-agent rotation", "bool"),
    ("G2", ("g2", "max_requests_per_minute"), "Max requests per minute", "int"),
    ("G2", ("g2", "backoff_base"), "Backoff base", "float"),
    ("G2", ("g2", "max_backoff"), "Max backoff (s)", "float"),
    ("G2", ("g2", "max_retries"), "Max retries", "int"),
    ("G2", ("g2", "jitter_range"), "Jitter range (two floats)", "list_float"),
    ("G2", ("g2", "use_playwright_fallback"), "Use Playwright fallback", "bool"),
    # APP STORE
    ("APP STORE", ("app_store", "app_ids"), "App IDs (Name=id, ...)", "dict_str_str"),
    ("APP STORE", ("app_store", "countries"), "Countries", "list_str"),
    ("APP STORE", ("app_store", "max_pages"), "Max pages", "int"),
    ("APP STORE", ("app_store", "max_items"), "Max items", "int"),
    ("APP STORE", ("app_store", "request_delay"), "Request delay (s)", "float"),
    ("APP STORE", ("app_store", "max_requests_per_minute"), "Max requests per minute", "int"),
    # PLAY STORE
    ("PLAY STORE", ("play_store", "package_names"), "Package names (Name=pkg, ...)", "dict_str_str"),
    ("PLAY STORE", ("play_store", "countries"), "Countries", "list_str"),
    ("PLAY STORE", ("play_store", "languages"), "Languages", "list_str"),
    ("PLAY STORE", ("play_store", "max_items"), "Max items", "int"),
    ("PLAY STORE", ("play_store", "request_delay"), "Request delay (s)", "float"),
    ("PLAY STORE", ("play_store", "max_requests_per_minute"), "Max requests per minute", "int"),
    # YOUTUBE
    ("YOUTUBE", ("youtube", "video_ids"), "Video IDs (Name=id1|id2, ...)", "dict_str_list"),
    ("YOUTUBE", ("youtube", "max_videos"), "Max videos", "int"),
    ("YOUTUBE", ("youtube", "max_comments_per_video"), "Max comments per video", "int"),
    ("YOUTUBE", ("youtube", "order"), "Order", "str"),
    # HACKER NEWS
    ("HACKER NEWS", ("hacker_news", "max_items"), "Max items", "int"),
    ("HACKER NEWS", ("hacker_news", "tags"), "Tags", "str"),
    ("HACKER NEWS", ("hacker_news", "request_delay"), "Request delay (s)", "float"),
    ("HACKER NEWS", ("hacker_news", "max_requests_per_minute"), "Max requests per minute", "int"),
    # GITHUB ISSUES
    ("GITHUB ISSUES", ("github_issues", "repos"), "Repos (Name=owner/repo|owner/repo, ...)", "dict_str_list"),
    ("GITHUB ISSUES", ("github_issues", "max_items"), "Max items", "int"),
    ("GITHUB ISSUES", ("github_issues", "request_delay"), "Request delay (s)", "float"),
    ("GITHUB ISSUES", ("github_issues", "max_requests_per_minute"), "Max requests per minute", "int"),
    # PRODUCT HUNT
    ("PRODUCT HUNT", ("product_hunt", "slugs"), "Slugs (Name=slug, ...)", "dict_str_str"),
    ("PRODUCT HUNT", ("product_hunt", "max_items"), "Max items", "int"),
    ("PRODUCT HUNT", ("product_hunt", "request_delay"), "Request delay (s)", "float"),
    ("PRODUCT HUNT", ("product_hunt", "max_requests_per_minute"), "Max requests per minute", "int"),
    ("PRODUCT HUNT", ("product_hunt", "use_playwright_fallback"), "Use Playwright fallback", "bool"),
    # STACK OVERFLOW
    ("STACK OVERFLOW", ("stack_overflow", "sites"), "Sites", "list_str"),
    ("STACK OVERFLOW", ("stack_overflow", "max_items"), "Max items", "int"),
    ("STACK OVERFLOW", ("stack_overflow", "request_delay"), "Request delay (s)", "float"),
    ("STACK OVERFLOW", ("stack_overflow", "max_requests_per_minute"), "Max requests per minute", "int"),
    # DEV.TO
    ("DEV.TO", ("dev_to", "max_items"), "Max items", "int"),
    ("DEV.TO", ("dev_to", "request_delay"), "Request delay (s)", "float"),
    ("DEV.TO", ("dev_to", "max_requests_per_minute"), "Max requests per minute", "int"),
    # SUPPORT FORUMS
    ("SUPPORT FORUMS", ("support_forums", "search_urls"), "Search URLs", "list_str"),
    ("SUPPORT FORUMS", ("support_forums", "max_items"), "Max items", "int"),
    ("SUPPORT FORUMS", ("support_forums", "request_delay"), "Request delay (s)", "float"),
    ("SUPPORT FORUMS", ("support_forums", "max_requests_per_minute"), "Max requests per minute", "int"),
    # CHANGELOGS
    ("CHANGELOGS", ("changelogs", "urls"), "URLs (Name=url1|url2, ...)", "dict_str_list"),
    ("CHANGELOGS", ("changelogs", "search_urls"), "Search URLs", "list_str"),
    ("CHANGELOGS", ("changelogs", "max_items"), "Max items", "int"),
    ("CHANGELOGS", ("changelogs", "request_delay"), "Request delay (s)", "float"),
    ("CHANGELOGS", ("changelogs", "max_requests_per_minute"), "Max requests per minute", "int"),
    # DISCORD EXPORTS
    ("DISCORD EXPORTS", ("discord_exports", "paths"), "Paths", "list_str"),
    ("DISCORD EXPORTS", ("discord_exports", "urls"), "URLs", "list_str"),
    ("DISCORD EXPORTS", ("discord_exports", "max_items"), "Max items", "int"),
    # LINKEDIN COMMENTS
    ("LINKEDIN COMMENTS", ("linkedin_comments", "paths"), "Paths", "list_str"),
    ("LINKEDIN COMMENTS", ("linkedin_comments", "urls"), "URLs", "list_str"),
    ("LINKEDIN COMMENTS", ("linkedin_comments", "max_items"), "Max items", "int"),
    # CLUSTERING
    ("CLUSTERING", ("clustering", "embedding_model"), "Embedding model", "str"),
    ("CLUSTERING", ("clustering", "umap_n_neighbors"), "UMAP n_neighbors", "int"),
    ("CLUSTERING", ("clustering", "umap_n_components"), "UMAP n_components", "int"),
    ("CLUSTERING", ("clustering", "hdbscan_min_cluster_size"), "HDBSCAN min cluster size", "int"),
    ("CLUSTERING", ("clustering", "hdbscan_min_samples"), "HDBSCAN min samples", "int"),
    # LLM
    ("LLM", ("llm", "model"), "Model", "str"),
    ("LLM", ("llm", "temperature"), "Temperature", "float"),
    ("LLM", ("llm", "max_tokens"), "Max tokens", "int"),
    # LOGGING
    ("LOGGING", ("logging", "level"), "Level", "str"),
    ("LOGGING", ("logging", "format"), "Format", "str"),
    # RESOLVER
    ("RESOLVER", ("resolver", "enabled"), "Enable auto-resolver", "bool"),
    ("RESOLVER", ("resolver", "cache_ttl_days"), "Cache TTL (days)", "int"),
    ("RESOLVER", ("resolver", "use_llm_disambiguator"), "Use LLM for tiebreaks", "bool"),
    ("RESOLVER", ("resolver", "use_sitemap_fallback"), "Use sitemap fallback", "bool"),
]


# ---------------------------------------------------------------------------
# Helpers — dict path access
# ---------------------------------------------------------------------------


def _get_path(data: dict, path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _set_path(data: dict, path: tuple[str, ...], value: Any) -> None:
    cur = data
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


# ---------------------------------------------------------------------------
# Display / parse per kind
# ---------------------------------------------------------------------------


def _display_default(kind: str, value: Any) -> str:
    if value is None:
        return ""
    if kind == "str":
        return str(value)
    if kind == "int" or kind == "float":
        return str(value)
    if kind == "bool":
        return "yes" if bool(value) else "no"
    if kind == "list_str":
        return ", ".join(str(x) for x in (value or []))
    if kind == "list_float":
        return ", ".join(str(x) for x in (value or []))
    if kind == "dict_str_str":
        return ", ".join(f"{k}={v}" for k, v in (value or {}).items())
    if kind == "dict_str_list":
        return ", ".join(
            f"{k}={'|'.join(str(x) for x in v)}" for k, v in (value or {}).items()
        )
    return str(value)


class _ParseError(ValueError):
    pass


def _parse(kind: str, raw: str) -> Any:
    text = raw.strip()
    if kind == "str":
        return text
    if kind == "int":
        try:
            return int(text)
        except ValueError as e:
            raise _ParseError(f"Expected an integer, got '{text}'") from e
    if kind == "float":
        try:
            return float(text)
        except ValueError as e:
            raise _ParseError(f"Expected a number, got '{text}'") from e
    if kind == "bool":
        lower = text.lower()
        if lower in ("y", "yes", "true", "1", "on"):
            return True
        if lower in ("n", "no", "false", "0", "off"):
            return False
        raise _ParseError(f"Expected yes/no, got '{text}'")
    if kind == "list_str":
        if not text:
            return []
        return [p.strip() for p in text.split(",") if p.strip()]
    if kind == "list_float":
        if not text:
            return []
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) != 2:
            raise _ParseError(f"Expected exactly two floats separated by comma, got {len(parts)}")
        try:
            return [float(p) for p in parts]
        except ValueError as e:
            raise _ParseError(f"Could not parse floats from '{text}'") from e
    if kind == "dict_str_str":
        if not text:
            return {}
        out: dict[str, str] = {}
        for pair in text.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise _ParseError(f"Expected 'key=value', got '{pair}'")
            k, v = pair.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k:
                raise _ParseError(f"Empty key in '{pair}'")
            out[k] = v
        return out
    if kind == "dict_str_list":
        if not text:
            return {}
        out2: dict[str, list[str]] = {}
        for pair in text.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise _ParseError(f"Expected 'key=val1|val2', got '{pair}'")
            k, v = pair.split("=", 1)
            k = k.strip()
            vals = [p.strip() for p in v.split("|") if p.strip()]
            if not k:
                raise _ParseError(f"Empty key in '{pair}'")
            out2[k] = vals
        return out2
    raise _ParseError(f"Unknown kind: {kind}")


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


def _print_welcome(path: str, existing: bool) -> None:
    msg = (
        "Welcome to Sift. Let's set up your config.yaml.\n"
        "Press Enter to accept defaults. Press Esc anytime to save or discard and exit."
    )
    if existing:
        msg += f"\nExisting values from {path} are shown as defaults."
    console.print()
    console.print(
        Panel.fit(Text(msg, style=f"bold {TEXT_PRIMARY}"), border_style=VIOLET)
    )
    console.print()


def _section_rule(title: str) -> None:
    console.print(Rule(f"[bold {VIOLET}]{title}[/bold {VIOLET}]", style=TEXT_MUTED, align="left"))
    console.print()


def _ask_one(label: str, default_text: str, kind: str) -> Optional[Any]:
    """Prompt until parse succeeds. Returns parsed value, or None on Esc."""
    from sift.ui.menu import read_line_with_escape

    pretty_label = f"  [{TEXT_PRIMARY}]{label}[/{TEXT_PRIMARY}]"
    while True:
        raw = read_line_with_escape(
            pretty_label,
            default=default_text,
            password=False,
            show_default=True,
        )
        if raw is None:
            return None
        try:
            return _parse(kind, raw)
        except _ParseError as e:
            console.print(f"  [{AMBER}]{ICON_DOT} {e}. Try again.[/{AMBER}]")


def run_config_wizard(path: str = "config.yaml") -> None:
    """Walk the user through every config.yaml field and save the result.

    - Existing values (if any) are pre-filled as defaults.
    - The ``products:`` section is passed through unchanged (slated for removal).
    - Esc opens a Save / Discard / Cancel panel (default Cancel).
    """
    existing: dict = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            existing = yaml.safe_load(f) or {}

    _print_welcome(path, existed := bool(existing))

    # Start from existing; fall back to DEFAULT_CONFIG for any unset path.
    merged: dict = {}
    if isinstance(existing, dict):
        merged.update(existing)

    last_section: Optional[str] = None
    i = 0
    while i < len(_ENTRIES):
        section, p, label, kind = _ENTRIES[i]
        if section != last_section:
            if last_section is not None:
                console.print()
            _section_rule(section)
            last_section = section

        current = _get_path(merged, p)
        if current is None:
            current = _get_path(DEFAULT_CONFIG, p)
        default_text = _display_default(kind, current)

        value = _ask_one(label, default_text, kind)
        if value is None:
            # Esc — Save / Discard / Cancel
            from sift.ui.menu import prompt_exit_choice
            choice = prompt_exit_choice()
            if choice == "save":
                console.print()
                _save_config(merged, path, existed)
                return
            if choice == "discard":
                console.print()
                console.print(
                    Panel(
                        f"[bold {AMBER}]{ICON_DOT} Changes discarded.[/bold {AMBER}]\n"
                        f"[{TEXT_SECONDARY}]Your config.yaml was not modified.[/{TEXT_SECONDARY}]",
                        border_style=AMBER,
                    )
                )
                console.print()
                return
            # cancel → re-draw section header and re-prompt same entry
            console.print()
            _section_rule(section)
            last_section = section
            continue

        _set_path(merged, p, value)
        i += 1

    console.print()
    _save_config(merged, path, existed)


def _save_config(merged: dict, path: str, existed: bool) -> None:
    """Write merged config to ``path``, backing up any prior file to .bak."""
    if existed and os.path.exists(path):
        try:
            os.replace(path, path + ".bak")
        except OSError:
            pass

    header = "# Sift Configuration\n# Generated by: sift init\n\n"
    body = yaml.safe_dump(merged, sort_keys=False, default_flow_style=False, indent=4)
    with open(path, "w") as f:
        f.write(header)
        f.write(body)

    extra = (
        f"\n[{TEXT_SECONDARY}]Previous version saved to {path}.bak[/{TEXT_SECONDARY}]"
        if existed
        else ""
    )
    console.print(
        Panel(
            f"[bold {EMERALD}]{ICON_DONE} Configuration saved to {path}[/bold {EMERALD}]{extra}",
            border_style=EMERALD,
        )
    )
    console.print()
