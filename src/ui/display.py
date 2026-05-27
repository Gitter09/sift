"""Rich-powered terminal display helpers for the Sift CLI.

All terminal formatting lives here. Pipeline and model code never touches Rich directly.
"""

from __future__ import annotations

import subprocess
from typing import List

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.models.report import ProductReport, ComparisonReport
from src.pipeline.report_generator import (
    generate_markdown_report,
    generate_comparison_markdown,
)
from src.config import Settings

console = Console()

# --- Style constants ---
SEVERITY_COLORS = {"high": "red", "medium": "yellow", "low": "green"}
SEVERITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
SOURCE_COLOR = "white"

# --- Aurora theme ---
# 7 stops, one per shape row — violet top fading to deep purple bottom
_AURORA_STOPS = [
    "#A78BFA",  # row 0  violet-400 (top)
    "#9B79F7",  # row 1
    "#8F67F4",  # row 2
    "#8355F1",  # row 3
    "#7743EE",  # row 4
    "#6B31EB",  # row 5
    "#5F1FE8",  # row 6  deep violet-purple (bottom)
]
ACCENT_COLOR = "#8B5CF6"   # mid-violet — used for borders, tagline, menu hints

SIFT_BANNER = (
    "███████╗    ██╗    ███████╗    ████████╗\n"
    "██╔════╝    ██║    ██╔════╝    ╚══██╔══╝\n"
    "███████╗    ██║    █████╗        ██║\n"
    "╚════██║    ██║    ██╔══╝        ██║\n"
    "███████║    ██║    ██║           ██║\n"
    "╚══════╝    ╚═╝    ╚═╝           ╚═╝\n"
    "\n"
    "Product Research Tool"
)

_PIXEL_MAPS = {
    # S: top bar anchors left edge, bottom bar anchors right edge — proper S flow
    'S': ['1111110', '1100000', '1100000', '0111110', '0000011', '0000011', '0111111'],
    # I/T: 3-pixel-wide stem (pixels 2-4 in 7-wide grid) for equal gaps left & right
    'I': ['1111111', '0011100', '0011100', '0011100', '0011100', '0011100', '1111111'],
    'F': ['1111111', '1100000', '1100000', '1111100', '1100000', '1100000', '1100000'],
    'T': ['1111111', '0011100', '0011100', '0011100', '0011100', '0011100', '0011100'],
}


def _render_sift_pixels(scale_x: int = 3, scale_y: int = 2, gap: int = 3) -> list[str]:
    word = 'SIFT'
    rows = []
    for row_idx in range(7):
        line = ''
        for i, ch in enumerate(word):
            if i > 0:
                line += ' ' * gap
            for pixel in _PIXEL_MAPS[ch][row_idx]:
                line += '█' * scale_x if pixel == '1' else ' ' * scale_x
        for _ in range(scale_y):
            rows.append(line)
    return rows


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("getsift")
    except Exception:
        return "0.1.0"


VERSION = _get_version()


def _git_info() -> str:
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], stderr=subprocess.DEVNULL
        ).decode().strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
        return f"{branch} · {commit}" if branch else commit
    except Exception:
        return ""


def _severity_text(severity: str | None) -> Text:
    sev = (severity or "medium").lower()
    color = SEVERITY_COLORS.get(sev, "white")
    icon = SEVERITY_ICONS.get(sev, "⚪")
    return Text(f"{icon} {sev}", style=color)


# ---------------------------------------------------------------------------
# Banner & config
# ---------------------------------------------------------------------------


def print_banner() -> None:
    lines = SIFT_BANNER.split("\n")
    gradient = ["bold bright_white", "bold bright_white", "bold white", "bold white", "white", "white"]
    for i, line in enumerate(lines[:6]):
        console.print(line, justify="center", style=gradient[i])
    for line in lines[6:]:
        if line.strip():
            console.print(line, justify="center", style="dim")
        else:
            console.print()
    console.print(f"v{_get_version()}", justify="center", style="dim")
    console.print()


def print_large_banner() -> None:
    # Pick scale based on terminal width: 3×2 needs ~96 cols, 2×2 needs ~68
    if console.width >= 96:
        scale_y = 2
        lines = _render_sift_pixels(scale_x=3, scale_y=scale_y, gap=3)
    elif console.width >= 68:
        scale_y = 2
        lines = _render_sift_pixels(scale_x=2, scale_y=scale_y, gap=2)
    else:
        scale_y = 1
        lines = _render_sift_pixels(scale_x=1, scale_y=scale_y, gap=2)

    # Each aurora stop repeats scale_y times (one stop per shape row)
    colors = [c for c in _AURORA_STOPS for _ in range(scale_y)]

    console.print()
    for line, color in zip(lines, colors):
        console.print(f"[bold {color}]{line}[/bold {color}]", justify="center")
    console.print()
    console.print(f"[{ACCENT_COLOR}]◈  Scrape · Cluster · Analyze  ◈[/{ACCENT_COLOR}]", justify="center")
    console.print(f"[dim {ACCENT_COLOR}]v{VERSION}[/dim {ACCENT_COLOR}]", justify="center")
    console.print()


def print_config_summary(settings: Settings, sources: list[str]) -> None:
    source_list = ", ".join(f"[{SOURCE_COLOR}]{s}[/{SOURCE_COLOR}]" for s in sources)
    disabled = settings.sources.disabled_sources
    disabled_str = ", ".join(disabled) if disabled else "none"

    content = (
        f"[bold]Sources:[/bold] {source_list}\n"
        f"[bold]LLM:[/bold] [yellow]{settings.llm.model}[/yellow]  "
        f"[bold]Embedding:[/bold] [yellow]{settings.clustering.embedding_model}[/yellow]\n"
        f"[bold]Disabled:[/bold] [dim]{disabled_str}[/dim]"
    )
    console.print(Panel(content, title="Configuration", border_style="white"))
    console.print()


# ---------------------------------------------------------------------------
# Progress context managers
# ---------------------------------------------------------------------------


class ScrapeProgress:
    """Context manager showing a spinner + bar for the scraping phase."""

    def __init__(self, total: int | None = None):
        self._total = total
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_id: TaskID | None = None

    def __enter__(self) -> "ScrapeProgress":
        self._progress.start()
        self._task_id = self._progress.add_task(
            f"[{SOURCE_COLOR}]Scraping[/{SOURCE_COLOR}]",
            total=self._total,
        )
        return self

    def __exit__(self, *args) -> None:
        self._progress.stop()

    def update_desc(self, description: str) -> None:
        if self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"[{SOURCE_COLOR}]{description}[/{SOURCE_COLOR}]",
            )

    def advance(self, amount: int = 1) -> None:
        if self._task_id is not None:
            self._progress.advance(self._task_id, amount)


class PipelineProgress:
    """Context manager showing a spinner + bar for pipeline stages."""

    def __init__(self, total_stages: int = 4):
        self._total = total_stages
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_id: TaskID | None = None

    def __enter__(self) -> "PipelineProgress":
        self._progress.start()
        self._task_id = self._progress.add_task(
            "[yellow]Pipeline[/yellow]",
            total=self._total,
        )
        return self

    def __exit__(self, *args) -> None:
        self._progress.stop()

    def stage(self, name: str) -> None:
        if self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"[yellow]{name}[/yellow]",
            )

    def set_total(self, total: int) -> None:
        if self._task_id is not None:
            self._progress.update(self._task_id, total=total)

    def advance(self) -> None:
        if self._task_id is not None:
            self._progress.advance(self._task_id, 1)


# ---------------------------------------------------------------------------
# Cluster & comparison displays
# ---------------------------------------------------------------------------


def print_cluster_summary(report: ProductReport) -> None:
    """Print a formatted table of clusters for a single product."""
    if not report.clusters:
        console.print(f"[dim]No clusters to display for {report.product}.[/dim]")
        return

    table = Table(
        title=f"Clusters — [bold]{report.product}[/bold] ({report.total_feedback_count} items)",
        box=box.ROUNDED,
        border_style="white",
        show_header=True,
        header_style="bold",
        title_style="bold",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Severity", width=10)
    table.add_column("Label", style="bold")
    table.add_column("Count", justify="right", width=6)
    table.add_column("Summary", max_width=80)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_clusters = sorted(
        report.clusters,
        key=lambda c: (severity_order.get((c.severity or "medium").lower(), 3), -c.size),
    )

    for i, cluster in enumerate(sorted_clusters, 1):
        table.add_row(
            str(i),
            _severity_text(cluster.severity),
            cluster.label or "Unnamed",
            str(cluster.size),
            cluster.summary or "",
        )

    console.print(table)
    console.print()


def print_comparison_summary(comparison: ComparisonReport) -> None:
    """Print a multi-product comparison summary with panels."""
    products_str = ", ".join(f"[bold]{p}[/bold]" for p in comparison.products)

    console.print(Rule("Competitive Comparison", style="dim"))
    console.print(f"Products: {products_str}")
    console.print()

    if comparison.competitive_insights:
        console.print(
            Panel(
                comparison.competitive_insights,
                title="Competitive Insights",
                border_style="yellow",
            )
        )
        console.print()

    if comparison.shared_pain_points:
        shared = "\n".join(f"• {p}" for p in comparison.shared_pain_points)
        console.print(Panel(shared, title="Shared Pain Points", border_style="red"))
        console.print()

    if comparison.unique_pain_points:
        for product, points in comparison.unique_pain_points.items():
            if points:
                items = "\n".join(f"• {p}" for p in points)
                console.print(
                    Panel(
                        items,
                        title=f"Unique to [bold]{product}[/bold]",
                        border_style="green",
                    )
                )
        console.print()


# ---------------------------------------------------------------------------
# Report preview & done banner
# ---------------------------------------------------------------------------


def print_report_preview(report: ProductReport) -> None:
    """Render the markdown report inline using Rich's Markdown renderer."""
    md = generate_markdown_report(report)
    console.print(Rule(f"Report Preview — {report.product}", style="dim"))
    console.print(Markdown(md))
    console.print()


def print_comparison_preview(comparison: ComparisonReport) -> None:
    """Render the comparison markdown inline."""
    md = generate_comparison_markdown(comparison)
    console.print(Rule("Comparison Report Preview", style="dim"))
    console.print(Markdown(md))
    console.print()


def print_done_banner(output_dir: str, files: list[str]) -> None:
    """Print a success banner listing saved report files."""
    file_list = "\n".join(f"  [dim]→[/dim] {f}" for f in files)
    console.print(
        Panel(
            file_list,
            border_style="green",
            title="[bold green]Done ✓[/bold green]",
            subtitle=f"[dim]{output_dir}/[/dim]",
        )
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def print_skip_warning(product: str, count: int) -> None:
    console.print(
        f"[yellow]⚠ Skipping '{product}' — only {count} items "
        f"(need ≥ 3 for clustering).[/yellow]"
    )


def print_scraper_warning(source: str, product: str) -> None:
    console.print(
        f"[yellow]⚠ {source} scraper failed for '{product}'. "
        f"Check logs for details.[/yellow]"
    )


def print_unknown_sources(unknown: list[str]) -> None:
    console.print(f"[yellow]Unknown source(s): {', '.join(unknown)}[/yellow]")


def print_no_scraper(source: str) -> None:
    console.print(f"[dim]No enabled scraper for '{source}'[/dim]")


def print_unconfigured_sources(sources: list[str]) -> None:
    formatted = ", ".join(sources)
    console.print(
        "[dim]Skipping unconfigured default source"
        f"{'s' if len(sources) != 1 else ''}: {formatted}[/dim]"
    )


def print_dedup_summary(total: int, duplicates: int, kept: int) -> None:
    dup_msg = f" (filtered {duplicates} duplicate{'s' if duplicates != 1 else ''})" if duplicates else ""
    console.print(f"[dim]Collected {kept} unique items from {total} total{dup_msg}.[/dim]")


def print_relevance_summary(total: int, rejected: int, kept: int, relaxed: bool = False) -> None:
    if total == 0:
        console.print("[dim]No items collected before relevance filtering.[/dim]")
        return
    relaxed_msg = " threshold relaxed" if relaxed else ""
    reject_msg = (
        f" (rejected {rejected} off-context item{'s' if rejected != 1 else ''}{relaxed_msg})"
        if rejected or relaxed
        else ""
    )
    console.print(f"[dim]Kept {kept} context-relevant items from {total} collected{reject_msg}.[/dim]")


def print_no_reports() -> None:
    console.print(
        "[yellow]No reports generated — no product had enough feedback for analysis.[/yellow]"
    )


def print_g2_proxy_warning() -> None:
    console.print(
        Panel(
            "G2 is protected by Cloudflare and cannot be reliably scraped without a paid proxy.\n\n"
            "To enable G2, add a proxy URL to your config or [bold].env[/bold]:\n\n"
            "  [dim]# config.yaml[/dim]\n"
            "  [bold]g2:[/bold]\n"
            "  [bold]  proxy_url:[/bold] https://user:pass@proxy.example.com\n\n"
            "  [dim]# .env[/dim]\n"
            "  [bold]G2_PROXY_URL[/bold]=https://user:pass@proxy.example.com\n\n"
            "Compatible services: [bold]ScraperAPI[/bold] · [bold]ZenRows[/bold] · "
            "[bold]BrightData[/bold] · [bold]Oxylabs[/bold]\n\n"
            "[dim]G2 will still be attempted but will likely return 0 results without a proxy.[/dim]",
            title="[yellow]G2 Requires a Paid Proxy[/yellow]",
            border_style="yellow",
        )
    )


def print_no_feedback_guidance(product: str, sources: list[str]) -> None:
    source_list = ", ".join(sources) if sources else "none"
    console.print(
        Panel(
            "No feedback items were collected.\n\n"
            f"Product: [bold]{product}[/bold]\n"
            f"Tried: [bold]{source_list}[/bold]\n\n"
            "Add product-specific config for higher-yield sources, for example:\n"
            "  • app_store.app_ids\n"
            "  • play_store.package_names\n"
            "  • github_issues.repos\n"
            "  • youtube.video_ids plus YOUTUBE_API_KEY\n"
            "  • support_forums.search_urls or changelogs.urls\n\n"
            "Use [bold]--verbose[/bold] to see blocked/network source diagnostics.",
            title="No Feedback Collected",
            border_style="yellow",
        )
    )
