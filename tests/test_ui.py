"""Tests for the Rich-powered UI display helpers."""

import io

import pytest
from rich.console import Console

from src.models.feedback import FeedbackItem
from src.models.cluster import ClusterResult
from src.models.report import ProductReport, ComparisonReport
from src.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_console() -> Console:
    """Create a Console that writes to a StringIO for assertion."""
    return Console(force_terminal=True, file=io.StringIO(), width=120)


def _capture(func, *args, **kwargs) -> str:
    """Call a display function with a captured Console and return its output."""
    output = io.StringIO()
    cap = Console(force_terminal=True, file=output, width=120)

    # Patch the module-level console temporarily
    import src.ui.display as display
    original_console = display.console
    display.console = cap
    try:
        func(*args, **kwargs)
    finally:
        display.console = original_console

    return output.getvalue()


def _make_cluster(
    cluster_id: int = 0,
    label: str = "Performance Issues",
    text: str = "App is too slow",
    severity: str = "high",
    size: int = 1,
) -> ClusterResult:
    items = [
        FeedbackItem(source="g2", product="TestApp", text=text)
        for _ in range(size)
    ]
    return ClusterResult(
        cluster_id=cluster_id,
        label=label,
        items=items,
        summary="Users report slowness across all pages.",
        severity=severity,
        representative_quotes=[text],
    )


def _make_report(product: str = "TestApp", clusters: list | None = None) -> ProductReport:
    if clusters is None:
        clusters = [_make_cluster()]
    return ProductReport(
        product=product,
        total_feedback_count=10,
        clusters=clusters,
        overall_insights="TestApp has notable performance gaps.",
        top_pain_points=["Performance", "Pricing"],
    )


# ---------------------------------------------------------------------------
# Banner & config
# ---------------------------------------------------------------------------


def test_print_banner():
    from src.ui.display import print_banner
    out = _capture(print_banner)
    assert "SIFT" in out or "Product Research" in out


def test_print_config_summary():
    from src.ui.display import print_config_summary
    settings = Settings()
    sources = ["g2", "hacker_news"]
    out = _capture(print_config_summary, settings, sources)
    assert "g2" in out
    assert "hacker_news" in out
    assert settings.llm.model in out


# ---------------------------------------------------------------------------
# Cluster & comparison displays
# ---------------------------------------------------------------------------


def test_print_cluster_summary():
    from src.ui.display import print_cluster_summary
    cluster = _make_cluster(label="Crash on launch", severity="high")
    report = _make_report("AppX", clusters=[cluster])

    out = _capture(print_cluster_summary, report)
    assert "AppX" in out
    assert "Crash on launch" in out
    assert "high" in out.lower() or "🔴" in out


def test_print_cluster_summary_no_clusters():
    from src.ui.display import print_cluster_summary
    report = _make_report("EmptyApp", clusters=[])
    out = _capture(print_cluster_summary, report)
    assert "No clusters" in out


def test_print_cluster_summary_sorts_by_severity():
    """High severity clusters should appear before low severity ones."""
    from src.ui.display import print_cluster_summary
    clusters = [
        _make_cluster(0, "Low issue", severity="low"),
        _make_cluster(1, "High issue", severity="high"),
        _make_cluster(2, "Medium issue", severity="medium"),
    ]
    report = _make_report("AppX", clusters=clusters)
    out = _capture(print_cluster_summary, report)
    high_idx = out.index("High issue")
    medium_idx = out.index("Medium issue")
    low_idx = out.index("Low issue")
    assert high_idx < medium_idx < low_idx


def test_print_comparison_summary():
    from src.ui.display import print_comparison_summary
    report1 = _make_report("Notion", clusters=[_make_cluster(label="Slow sync", severity="high")])
    report2 = _make_report("Obsidian", clusters=[_make_cluster(label="Plugin crashes", severity="medium")])
    comp = ComparisonReport(
        products=["Notion", "Obsidian"],
        product_reports={"Notion": report1, "Obsidian": report2},
        shared_pain_points=["Learning curve"],
        unique_pain_points={"Notion": ["Slow sync"], "Obsidian": ["Plugin crashes"]},
        competitive_insights="Notion is better for teams, Obsidian for individuals.",
    )
    out = _capture(print_comparison_summary, comp)
    assert "Notion" in out
    assert "Obsidian" in out
    assert "Learning curve" in out


# ---------------------------------------------------------------------------
# Progress context managers (smoke tests — they print via transient bars)
# ---------------------------------------------------------------------------


def test_scrape_progress_context():
    from src.ui.display import ScrapeProgress
    with ScrapeProgress(total=2) as progress:
        progress.update_desc("Scraping g2 › Notion")
        progress.advance()
        progress.update_desc("Scraping hacker_news › Notion")
        progress.advance()
    # Should not raise


def test_pipeline_progress_context():
    from src.ui.display import PipelineProgress
    with PipelineProgress(total_stages=4) as progress:
        progress.stage("Embedding")
        progress.advance()
        progress.stage("Clustering")
        progress.advance()
        progress.stage("LLM Analysis")
        progress.advance()
        progress.stage("Insights")
        progress.advance()
    # Should not raise


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def test_print_skip_warning():
    from src.ui.display import print_skip_warning
    out = _capture(print_skip_warning, "TestApp", 2)
    assert "Skipping" in out
    assert "TestApp" in out
    assert "2" in out


def test_print_scraper_warning():
    from src.ui.display import print_scraper_warning
    out = _capture(print_scraper_warning, "g2", "TestApp")
    assert "g2" in out
    assert "TestApp" in out
    assert "failed" in out.lower()


def test_print_unknown_sources():
    from src.ui.display import print_unknown_sources
    out = _capture(print_unknown_sources, ["bad_source", "fake"])
    assert "bad_source" in out
    assert "fake" in out


def test_print_no_scraper():
    from src.ui.display import print_no_scraper
    out = _capture(print_no_scraper, "nonexistent")
    assert "nonexistent" in out


def test_print_unconfigured_sources():
    from src.ui.display import print_unconfigured_sources
    out = _capture(print_unconfigured_sources, ["app_store", "youtube"])
    assert "app_store" in out
    assert "youtube" in out
    assert "unconfigured" in out


def test_print_dedup_summary():
    from src.ui.display import print_dedup_summary
    out = _capture(print_dedup_summary, 100, 5, 95)
    assert "95" in out
    assert "100" in out
    assert "5" in out


def test_print_dedup_summary_no_duplicates():
    from src.ui.display import print_dedup_summary
    out = _capture(print_dedup_summary, 50, 0, 50)
    # Should not mention "filtered" when duplicates=0
    assert "filtered" not in out


def test_print_no_reports():
    from src.ui.display import print_no_reports
    out = _capture(print_no_reports)
    assert "No reports" in out


def test_print_no_feedback_guidance():
    from src.ui.display import print_no_feedback_guidance
    out = _capture(print_no_feedback_guidance, "Notion", ["g2", "hacker_news"])
    assert "No feedback" in out
    assert "Notion" in out
    assert "app_store.app_ids" in out
    assert "--verbose" in out


def test_print_done_banner():
    from src.ui.display import print_done_banner
    out = _capture(print_done_banner, "output", ["output/appx_report.md", "output/appx_report.json"])
    assert "Done" in out
    assert "appx_report.md" in out
