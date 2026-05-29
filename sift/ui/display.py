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

from sift.models import ProductReport, ComparisonReport
from sift.pipeline.report_generator import (
    generate_markdown_report,
    generate_comparison_markdown,
)
from sift.config import Settings
from sift.ui.theme import (
    ACCENT_COLOR,
    AMBER,
    AURORA_STOPS,
    BORDER_DIM,
    CYAN,
    EMERALD,
    ICON_BULLET,
    ICON_DIAMOND,
    ICON_DONE,
    ICON_DOT,
    ICON_SELECT,
    ICON_WARN,
    ROSE,
    SEVERITY_COLORS,
    SEVERITY_DOTS,
    SOURCE_COLOR,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    VIOLET,
    VIOLET_DIM,
)

console = Console()

# Backward-compatible exports (modules import these from display)
__all__ = [
    "ACCENT_COLOR", "SEVERITY_COLORS", "SEVERITY_DOTS", "SOURCE_COLOR",
    "VERSION", "console",
    "print_banner", "print_large_banner", "print_config_summary",
    "print_cluster_summary", "print_comparison_summary",
    "print_report_preview", "print_comparison_preview",
    "print_done_banner", "print_skip_warning", "print_scraper_warning",
    "print_unknown_sources", "print_no_scraper", "print_unconfigured_sources",
    "print_dedup_summary", "print_relevance_summary", "print_no_reports",
    "print_g2_proxy_warning", "print_no_feedback_guidance",
    "ScrapeProgress", "PipelineProgress",
]

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
    'S': ['1111110', '1100000', '1100000', '0111110', '0000011', '0000011', '0111111'],
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
                line += '\u2588' * scale_x if pixel == '1' else ' ' * scale_x
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
        return f"{branch} {ICON_DOT} {commit}" if branch else commit
    except Exception:
        return ""


def _severity_text(severity: str | None) -> Text:
    sev = (severity or "medium").lower()
    color = SEVERITY_COLORS.get(sev, TEXT_PRIMARY)
    dot = SEVERITY_DOTS.get(sev, SEVERITY_DOTS["medium"])
    return Text.from_markup(f"{dot} {sev}", style=color)


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
    console.print(f"v{_get_version()}", justify="center", style=f"dim {TEXT_SECONDARY}")
    console.print()


def print_large_banner() -> None:
    # Pick scale based on terminal width: 3x2 needs ~96 cols, 2x2 needs ~68
    if console.width >= 96:
        scale_y = 2
        lines = _render_sift_pixels(scale_x=3, scale_y=scale_y, gap=3)
    elif console.width >= 68:
        scale_y = 2
        lines = _render_sift_pixels(scale_x=2, scale_y=scale_y, gap=2)
    else:
        scale_y = 1
        lines = _render_sift_pixels(scale_x=1, scale_y=scale_y, gap=2)

    colors = [c for c in AURORA_STOPS for _ in range(scale_y)]

    # Subtle glow aura — faint violet lines above and below the wordmark
    console.print()
    # Pick the first column width to size the glow line
    sample_line = lines[0]
    glow_len = len(sample_line.rstrip()) if sample_line else 40
    glow = f"[dim {VIOLET_DIM}]{'─' * min(glow_len, 80)}[/dim {VIOLET_DIM}]"
    console.print(glow, justify="center")
    console.print()

    for line, color in zip(lines, colors):
        console.print(f"[bold {color}]{line}[/bold {color}]", justify="center")

    console.print()
    console.print(glow, justify="center")
    console.print()
    console.print(f"[{VIOLET}]{ICON_DIAMOND}  Scrape {ICON_DOT} Cluster {ICON_DOT} Analyze  {ICON_DIAMOND}[/{VIOLET}]", justify="center")
    console.print(f"[dim {VIOLET}]v{VERSION}[/dim {VIOLET}]", justify="center")
    console.print()


def print_config_summary(settings: Settings, sources: list[str]) -> None:
    source_list = ", ".join(f"[{SOURCE_COLOR}]{s}[/{SOURCE_COLOR}]" for s in sources)
    disabled = settings.sources.disabled_sources
    disabled_str = ", ".join(disabled) if disabled else "none"

    content = (
        f"[bold]Sources:[/bold] {source_list}\n"
        f"[bold]LLM:[/bold] [{CYAN}]{settings.llm.model}[/{CYAN}]  "
        f"[bold]Embedding:[/bold] [{CYAN}]{settings.clustering.embedding_model}[/{CYAN}]\n"
        f"[bold]Disabled:[/bold] [{TEXT_SECONDARY}]{disabled_str}[/{TEXT_SECONDARY}]"
    )
    console.print(Panel(content, title="Configuration", border_style=VIOLET))
    console.print()


# ---------------------------------------------------------------------------
# Progress context managers
# ---------------------------------------------------------------------------


class ScrapeProgress:
    """Context manager showing a spinner + bar for the scraping phase.

    The bar advances by one whole slot per ``(source, product)`` pair. Inside
    a slot, ``start_estimated(source)`` drives the fill smoothly using the
    EMA-backed expected duration in :mod:`sift.ui.timings`; ``advance()``
    folds the observed duration back into the EMA so subsequent runs are
    more accurate.
    """

    def __init__(self, total: int | None = None):
        self._total = total
        self._progress = Progress(
            SpinnerColumn(style=CYAN),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style=BORDER_DIM, complete_style=CYAN),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_id: TaskID | None = None
        self._slot: int = 0
        self._active_key: str | None = None
        self._active_task: "EstimatedTask | None" = None

    def __enter__(self) -> "ScrapeProgress":
        self._progress.start()
        self._task_id = self._progress.add_task(
            f"[{VIOLET}]Scraping[/{VIOLET}]",
            total=self._total,
        )
        return self

    def __exit__(self, *args) -> None:
        self._progress.stop()

    def update_desc(self, description: str) -> None:
        if self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"[{VIOLET}]{description}[/{VIOLET}]",
            )

    def start_estimated(self, source: str) -> "EstimatedTask":
        """Begin smoothly filling the current slot for ``source``.

        Use as ``with scrape_progress.start_estimated(src): scraper.scrape(...)``.
        """
        from sift.ui._estimator import EstimatedTask
        from sift.ui import timings

        assert self._task_id is not None, "ScrapeProgress used outside `with`"
        self._active_key = source
        self._active_task = EstimatedTask(
            self._progress,
            self._task_id,
            expected_seconds=timings.get("scrape", source),
            start_completed=float(self._slot),
        )
        return self._active_task

    def advance(self, amount: int = 1) -> None:
        if self._task_id is None:
            return
        # If a slot just finished with an active estimator, fold the real
        # duration into the EMA store so the next run uses it. Only on
        # success — a scraper that raised after 0.5s shouldn't pull the
        # learned duration toward 0.5s for a slot whose real cost is 60s.
        if self._active_task is not None and self._active_key is not None:
            if self._active_task.succeeded:
                from sift.ui import timings

                timings.record("scrape", self._active_key, self._active_task.elapsed)
            self._active_task = None
            self._active_key = None
        self._slot += amount
        self._progress.update(self._task_id, completed=float(self._slot))


class PipelineProgress:
    """Context manager showing a spinner + bar for pipeline stages.

    Like :class:`ScrapeProgress`, but slots correspond to pipeline stages
    (embedding, clustering, one per cluster analysed, insights). Each stage
    has its own EMA key so the per-stage estimate improves over time.
    """

    def __init__(self, total_stages: int = 4):
        self._total = total_stages
        self._progress = Progress(
            SpinnerColumn(style=CYAN),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style=VIOLET_DIM, complete_style=CYAN),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_id: TaskID | None = None
        self._slot: int = 0
        self._active_key: str | None = None
        self._active_task: "EstimatedTask | None" = None

    def __enter__(self) -> "PipelineProgress":
        self._progress.start()
        self._task_id = self._progress.add_task(
            f"[{CYAN}]Pipeline[/{CYAN}]",
            total=self._total,
        )
        return self

    def __exit__(self, *args) -> None:
        self._progress.stop()

    def stage(self, name: str) -> None:
        if self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"[{CYAN}]{name}[/{CYAN}]",
            )

    def set_total(self, total: int) -> None:
        if self._task_id is not None:
            self._progress.update(self._task_id, total=total)

    def start_estimated(self, stage_key: str) -> "EstimatedTask":
        from sift.ui._estimator import EstimatedTask
        from sift.ui import timings

        assert self._task_id is not None, "PipelineProgress used outside `with`"
        self._active_key = stage_key
        self._active_task = EstimatedTask(
            self._progress,
            self._task_id,
            expected_seconds=timings.get("pipeline", stage_key),
            start_completed=float(self._slot),
        )
        return self._active_task

    def advance(self) -> None:
        if self._task_id is None:
            return
        if self._active_task is not None and self._active_key is not None:
            if self._active_task.succeeded:
                from sift.ui import timings

                timings.record("pipeline", self._active_key, self._active_task.elapsed)
            self._active_task = None
            self._active_key = None
        self._slot += 1
        self._progress.update(self._task_id, completed=float(self._slot))


# ---------------------------------------------------------------------------
# Cluster & comparison displays
# ---------------------------------------------------------------------------


def print_cluster_summary(report: ProductReport) -> None:
    """Print a formatted table of clusters for a single product."""
    if not report.clusters:
        console.print(f"[dim]No clusters to display for {report.product}.[/dim]")
        return

    table = Table(
        title=f"Clusters {ICON_DOT} [bold {TEXT_PRIMARY}]{report.product}[/bold {TEXT_PRIMARY}] ({report.total_feedback_count} items)",
        box=box.ROUNDED,
        border_style=VIOLET_DIM,
        show_header=True,
        header_style=f"bold {VIOLET}",
        title_style=f"bold {TEXT_PRIMARY}",
    )
    table.add_column("#", style=f"dim {TEXT_MUTED}", width=3, justify="right")
    table.add_column("Severity", width=12)
    table.add_column("Label", style=f"bold {TEXT_PRIMARY}")
    table.add_column("Count", justify="right", width=6, style=TEXT_SECONDARY)
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
    console.print(Rule(style=BORDER_DIM))
    console.print()


def print_comparison_summary(comparison: ComparisonReport) -> None:
    """Print a multi-product comparison summary with panels."""
    products_str = "  ".join(
        f"[{CYAN}]{ICON_DOT}[/{CYAN}] [bold {TEXT_PRIMARY}]{p}[/bold {TEXT_PRIMARY}]"
        for p in comparison.products
    )

    console.print(Rule(style=BORDER_DIM))
    console.print(f"[bold {TEXT_SECONDARY}]PRODUCTS[/bold {TEXT_SECONDARY}]")
    console.print(products_str)
    console.print()

    if comparison.competitive_insights:
        console.print(
            Panel(
                comparison.competitive_insights,
                title=f"[{AMBER}]Competitive Insights[/{AMBER}]",
                border_style=AMBER,
            )
        )
        console.print()

    if comparison.shared_pain_points:
        shared = "\n".join(f"  {ICON_SELECT} {p}" for p in comparison.shared_pain_points)
        console.print(
            Panel(
                shared,
                title=f"[{ROSE}]Shared Pain Points[/{ROSE}]",
                border_style=ROSE,
            )
        )
        console.print()

    if comparison.unique_pain_points:
        for product, points in comparison.unique_pain_points.items():
            if points:
                items = "\n".join(f"  {ICON_SELECT} {p}" for p in points)
                console.print(
                    Panel(
                        items,
                        title=f"[{EMERALD}]Unique to {product}[/{EMERALD}]",
                        border_style=EMERALD,
                    )
                )
        console.print()


# ---------------------------------------------------------------------------
# Report preview & done banner
# ---------------------------------------------------------------------------


def print_report_preview(report: ProductReport) -> None:
    """Render the markdown report inline using Rich's Markdown renderer."""
    md = generate_markdown_report(report)
    console.print(Rule(f"Report Preview {ICON_DOT} {report.product}", style=BORDER_DIM))
    console.print(Markdown(md))
    console.print()


def print_comparison_preview(comparison: ComparisonReport) -> None:
    """Render the comparison markdown inline."""
    md = generate_comparison_markdown(comparison)
    console.print(Rule(f"Comparison Report Preview", style=BORDER_DIM))
    console.print(Markdown(md))
    console.print()


def print_done_banner(output_dir: str, files: list[str]) -> None:
    """Print a success banner listing saved report files."""
    file_list = "\n".join(f"  [{TEXT_MUTED}]{ICON_BULLET}[/{TEXT_MUTED}] {f}" for f in files)
    console.print(
        Panel(
            file_list,
            border_style=VIOLET,
            title=f"[bold {EMERALD}]{ICON_DONE} Done[/bold {EMERALD}]",
            subtitle=f"[dim]{output_dir}/[/dim]",
        )
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def print_skip_warning(product: str, count: int) -> None:
    console.print(
        Panel(
            f"Skipping [{TEXT_PRIMARY}]{product}[/{TEXT_PRIMARY}] {ICON_WARN} only {count} items "
            f"(need \u2265 3 for clustering).",
            border_style=AMBER,
            title=f"[{AMBER}]Skipped[/{AMBER}]",
        )
    )


def print_scraper_warning(source: str, product: str) -> None:
    console.print(
        Panel(
            f"[{TEXT_PRIMARY}]{source}[/{TEXT_PRIMARY}] scraper failed for "
            f"[{TEXT_PRIMARY}]{product}[/{TEXT_PRIMARY}]. Check logs for details.",
            border_style=ROSE,
            title=f"[{ROSE}]Scraper Error[/{ROSE}]",
        )
    )


def print_unknown_sources(unknown: list[str]) -> None:
    console.print(
        f"[{AMBER}]{ICON_WARN} Unknown source(s): {', '.join(unknown)}[/{AMBER}]"
    )


def print_no_scraper(source: str) -> None:
    console.print(f"[{TEXT_MUTED}]No enabled scraper for '{source}'[/{TEXT_MUTED}]")


def print_unconfigured_sources(sources: list[str]) -> None:
    formatted = ", ".join(sources)
    console.print(
        f"[{TEXT_MUTED}]Skipping unconfigured default source"
        f"{'s' if len(sources) != 1 else ''}: {formatted}[/{TEXT_MUTED}]"
    )


def print_dedup_summary(total: int, duplicates: int, kept: int) -> None:
    dup_msg = (
        f" [{ICON_DOT}] {duplicates} duplicate{'s' if duplicates != 1 else ''} filtered"
        if duplicates else ""
    )
    console.print(
        f"[{TEXT_SECONDARY}]{kept} unique items from {total} collected{dup_msg}.[/{TEXT_SECONDARY}]"
    )


def print_relevance_summary(total: int, rejected: int, kept: int, relaxed: bool = False) -> None:
    if total == 0:
        console.print(f"[{TEXT_SECONDARY}]No items collected before relevance filtering.[/{TEXT_SECONDARY}]")
        return
    relaxed_msg = " (threshold relaxed)" if relaxed else ""
    reject_msg = (
        f" [{ICON_DOT}] {rejected} off-context rejected{relaxed_msg}"
        if rejected or relaxed
        else ""
    )
    console.print(
        f"[{TEXT_SECONDARY}]{kept} context-relevant items from {total} collected{reject_msg}.[/{TEXT_SECONDARY}]"
    )


def print_disambiguation_summary(collected: int, l1_stats, dstats) -> None:
    """Per-layer breakdown of the three-layer content disambiguator."""
    if collected == 0:
        console.print(f"[{TEXT_SECONDARY}]No items collected before disambiguation.[/{TEXT_SECONDARY}]")
        return

    gate = ""
    if dstats.gated or dstats.over_cap:
        gate = f" [{ICON_DOT}] LLM gate {dstats.gate_yes}✓/{dstats.gate_no}✗"
        if dstats.over_cap:
            gate += f" ({dstats.over_cap} by score)"
    safety = " (safety net)" if dstats.safety_net_triggered else ""
    anchor = "anchor" if dstats.anchor_used else "heuristic-only"

    console.print(
        f"[{TEXT_SECONDARY}]{dstats.final_kept} product-relevant items from {collected} collected "
        f"[{ICON_DOT}] L1 dropped {l1_stats.dropped} [{ICON_DOT}] {anchor} keep {dstats.auto_kept}"
        f"/reject {dstats.auto_rejected}{gate}{safety}.[/{TEXT_SECONDARY}]"
    )


def print_no_reports() -> None:
    console.print(
        Panel(
            "No product had enough feedback for analysis (minimum 3 items required).",
            border_style=AMBER,
            title=f"[{AMBER}]No Reports Generated[/{AMBER}]",
        )
    )


def print_g2_proxy_warning() -> None:
    console.print(
        Panel(
            "G2 is protected by Cloudflare and cannot be reliably scraped without a paid proxy.\n\n"
            "To enable G2, add a proxy URL to your config or [bold].env[/bold]:\n\n"
            f"  [{TEXT_MUTED}]# config.yaml[/{TEXT_MUTED}]\n"
            "  [bold]g2:[/bold]\n"
            "  [bold]  proxy_url:[/bold] ****************************************\n\n"
            f"  [{TEXT_MUTED}]# .env[/{TEXT_MUTED}]\n"
            "  [bold]G2_PROXY_URL[/bold]=****************************************\n\n"
            "Compatible services: [bold]ScraperAPI[/bold] "
            f"{ICON_DOT} [bold]ZenRows[/bold] "
            f"{ICON_DOT} [bold]BrightData[/bold] "
            f"{ICON_DOT} [bold]Oxylabs[/bold]\n\n"
            f"[{TEXT_SECONDARY}]G2 will still be attempted but will likely return 0 results "
            f"without a proxy.[/{TEXT_SECONDARY}]",
            title=f"[{AMBER}]G2 Requires a Paid Proxy[/{AMBER}]",
            border_style=AMBER,
        )
    )


def print_no_feedback_guidance(product: str, sources: list[str]) -> None:
    source_list = ", ".join(sources) if sources else "none"
    console.print(
        Panel(
            "No feedback items were collected.\n\n"
            f"Product: [bold {TEXT_PRIMARY}]{product}[/bold {TEXT_PRIMARY}]\n"
            f"Tried: [bold {TEXT_PRIMARY}]{source_list}[/bold {TEXT_PRIMARY}]\n\n"
            "Add product-specific config for higher-yield sources:\n"
            "  \u2022 app_store.app_ids\n"
            "  \u2022 play_store.package_names\n"
            "  \u2022 github_issues.repos\n"
            "  \u2022 youtube.video_ids plus YOUTUBE_API_KEY\n"
            "  \u2022 support_forums.search_urls or changelogs.urls\n\n"
            f"[{TEXT_SECONDARY}]Use [{TEXT_PRIMARY}]--verbose[/{TEXT_PRIMARY}] "
            f"to see blocked/network source diagnostics.[/{TEXT_SECONDARY}]",
            title=f"[{AMBER}]No Feedback Collected[/{AMBER}]",
            border_style=AMBER,
        )
    )
