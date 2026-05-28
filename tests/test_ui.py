"""Tests for the Rich-powered UI display helpers."""

import io

import pytest
from rich.console import Console

from sift.models import (
    ClusterResult,
    ComparisonReport,
    FeedbackItem,
    ProductReport,
)
from sift.config import Settings


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
    import sift.ui.display as display
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
    from sift.ui.display import print_banner
    out = _capture(print_banner)
    assert "SIFT" in out or "Product Research" in out


def test_print_config_summary():
    from sift.ui.display import print_config_summary
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
    from sift.ui.display import print_cluster_summary
    cluster = _make_cluster(label="Crash on launch", severity="high")
    report = _make_report("AppX", clusters=[cluster])

    out = _capture(print_cluster_summary, report)
    assert "AppX" in out
    assert "Crash on launch" in out
    assert "high" in out.lower()


def test_print_cluster_summary_no_clusters():
    from sift.ui.display import print_cluster_summary
    report = _make_report("EmptyApp", clusters=[])
    out = _capture(print_cluster_summary, report)
    assert "No clusters" in out


def test_print_cluster_summary_sorts_by_severity():
    """High severity clusters should appear before low severity ones."""
    from sift.ui.display import print_cluster_summary
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
    from sift.ui.display import print_comparison_summary
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
    from sift.ui.display import ScrapeProgress
    with ScrapeProgress(total=2) as progress:
        progress.update_desc("Scraping g2 › Notion")
        progress.advance()
        progress.update_desc("Scraping hacker_news › Notion")
        progress.advance()
    # Should not raise


def test_pipeline_progress_context():
    from sift.ui.display import PipelineProgress
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
    from sift.ui.display import print_skip_warning
    out = _capture(print_skip_warning, "TestApp", 2)
    assert "Skipping" in out
    assert "TestApp" in out
    assert "2" in out


def test_print_scraper_warning():
    from sift.ui.display import print_scraper_warning
    out = _capture(print_scraper_warning, "g2", "TestApp")
    assert "g2" in out
    assert "TestApp" in out
    assert "failed" in out.lower()


def test_print_unknown_sources():
    from sift.ui.display import print_unknown_sources
    out = _capture(print_unknown_sources, ["bad_source", "fake"])
    assert "bad_source" in out
    assert "fake" in out


def test_print_no_scraper():
    from sift.ui.display import print_no_scraper
    out = _capture(print_no_scraper, "nonexistent")
    assert "nonexistent" in out


def test_print_unconfigured_sources():
    from sift.ui.display import print_unconfigured_sources
    out = _capture(print_unconfigured_sources, ["app_store", "youtube"])
    assert "app_store" in out
    assert "youtube" in out
    assert "unconfigured" in out


def test_print_dedup_summary():
    from sift.ui.display import print_dedup_summary
    out = _capture(print_dedup_summary, 100, 5, 95)
    assert "95" in out
    assert "100" in out
    assert "5" in out


def test_print_dedup_summary_no_duplicates():
    from sift.ui.display import print_dedup_summary
    out = _capture(print_dedup_summary, 50, 0, 50)
    # Should not mention "filtered" when duplicates=0
    assert "filtered" not in out


def test_print_relevance_summary():
    from sift.ui.display import print_relevance_summary
    out = _capture(print_relevance_summary, 20, 4, 16)
    assert "16" in out
    assert "20" in out
    assert "off-context" in out


def test_print_no_reports():
    from sift.ui.display import print_no_reports
    out = _capture(print_no_reports)
    assert "No Reports Generated" in out or "No reports" in out


def test_print_no_feedback_guidance():
    from sift.ui.display import print_no_feedback_guidance
    out = _capture(print_no_feedback_guidance, "Notion", ["g2", "hacker_news"])
    assert "No feedback" in out
    assert "Notion" in out
    assert "app_store.app_ids" in out
    assert "--verbose" in out


def test_print_done_banner():
    from sift.ui.display import print_done_banner
    out = _capture(print_done_banner, "output", ["output/appx_report.md", "output/appx_report.json"])
    assert "Done" in out
    assert "appx_report.md" in out


# ---------------------------------------------------------------------------
# Setup wizard: Escape-to-exit with Save/Discard/Cancel popup
# ---------------------------------------------------------------------------


def test_setup_wizard_discard_does_not_write_env(tmp_path, monkeypatch):
    """Pressing Esc on the first prompt and choosing Discard must not touch .env."""
    import sift.ui.setup as setup_mod

    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_mod, "_ENV_PATH", env_path)

    def fake_read_line(label, default="", password=False, show_default=True):
        return None  # simulate Esc on the very first prompt

    save_calls = []

    def fake_save_env(new_values, existing):
        save_calls.append(dict(new_values))

    monkeypatch.setattr("sift.ui.menu.read_line_with_escape", fake_read_line)
    monkeypatch.setattr("sift.ui.menu.prompt_exit_choice", lambda: "discard")
    monkeypatch.setattr(setup_mod, "_save_env", fake_save_env)

    setup_mod.run_setup_wizard()

    assert save_calls == []
    assert not env_path.exists()


def test_setup_wizard_save_persists_partial_values(tmp_path, monkeypatch):
    """Entering one value then Esc + Save must call _save_env with that value."""
    import sift.ui.setup as setup_mod

    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_mod, "_ENV_PATH", env_path)

    calls = {"n": 0}

    def fake_read_line(label, default="", password=False, show_default=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return "sk-test-123"
        return None  # Esc on the second prompt

    save_calls = []

    def fake_save_env(new_values, existing):
        save_calls.append(dict(new_values))

    monkeypatch.setattr("sift.ui.menu.read_line_with_escape", fake_read_line)
    monkeypatch.setattr("sift.ui.menu.prompt_exit_choice", lambda: "save")
    monkeypatch.setattr(setup_mod, "_save_env", fake_save_env)

    setup_mod.run_setup_wizard()

    assert len(save_calls) == 1
    assert save_calls[0].get("LLM_API_KEY") == "sk-test-123"


def test_setup_wizard_cancel_resumes(tmp_path, monkeypatch):
    """Esc + Cancel must resume at the same prompt without saving."""
    import sift.ui.setup as setup_mod

    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_mod, "_ENV_PATH", env_path)

    # Sequence: prompt 1 returns None (Esc), then on resume returns a value,
    # then every subsequent prompt returns "" to walk through quickly.
    answers = iter([None, "sk-resumed"] + [""] * 20)

    def fake_read_line(label, default="", password=False, show_default=True):
        return next(answers)

    choices = iter(["cancel"])
    monkeypatch.setattr("sift.ui.menu.read_line_with_escape", fake_read_line)
    monkeypatch.setattr("sift.ui.menu.prompt_exit_choice", lambda: next(choices))

    save_calls = []

    def fake_save_env(new_values, existing):
        save_calls.append(dict(new_values))

    monkeypatch.setattr(setup_mod, "_save_env", fake_save_env)

    setup_mod.run_setup_wizard()

    # Walked all the way through and saved at the end.
    assert len(save_calls) == 1
    assert save_calls[0].get("LLM_API_KEY") == "sk-resumed"
