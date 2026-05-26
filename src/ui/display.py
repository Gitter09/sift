"""Rich-powered terminal display helpers for the Sift CLI.

All terminal formatting lives here. Pipeline and model code never touches Rich directly.
"""

from __future__ import annotations

from typing import List

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
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

LARGE_BANNER = (
    "███████╗       ██╗       ███████╗       ████████╗\n"
    "██╔════╝       ██║       ██╔════╝       ╚══██╔══╝\n"
    "███████╗       ██║       █████╗           ██║\n"
    "╚════██║       ██║       ██╔══╝           ██║\n"
    "███████║       ██║       ██║              ██║\n"
    "╚══════╝       ╚═╝       ╚═╝              ╚═╝\n"
    "\n"
    "Scrape · Cluster · Analyze Product Feedback"
)


def _get_version() -> str:
    """Return the installed package version, or a fallback."""
    try:
        from importlib.metadata import version
        return version("getsift")
    except Exception:
        return "0.1.0"


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
    console.print("\n" * 10, end="")
    lines = LARGE_BANNER.split("\n")
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
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
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
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
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


def print_no_reports() -> None:
    console.print(
        "[yellow]No reports generated — no product had enough feedback for analysis.[/yellow]"
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
