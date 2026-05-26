import asyncio
import logging
import sys
import types

from src.config import LLMConfig
from src.models.cluster import ClusterResult
from src.models.feedback import FeedbackItem
from src.models.report import ProductReport
from src.pipeline.analyzer import Analyzer
from src.pipeline.comparator import Comparator
from src.pipeline.http_client import BrowserFetcher, HttpResponse
from src.pipeline.rate_limiter import RateLimiter


def _cluster(cluster_id: int = 0) -> ClusterResult:
    return ClusterResult(
        cluster_id=cluster_id,
        items=[
            FeedbackItem(
                source="test",
                product="Notion",
                text="Sync is unreliable and pages sometimes take a long time to load.",
            )
        ],
    )


def test_analyzer_missing_key_uses_fallback_without_traceback(caplog):
    analyzer = Analyzer(LLMConfig(api_key=""))
    cluster = _cluster(7)

    with caplog.at_level(logging.WARNING, logger="src.pipeline.analyzer"):
        analyzed = analyzer.analyze_cluster(cluster)
        insights = analyzer.generate_overall_insights("Notion", [analyzed])

    assert analyzed.label == "Cluster 7"
    assert analyzed.severity == "medium"
    assert "LLM API key is not configured" in analyzed.summary
    assert insights["top_pain_points"] == ["Cluster 7"]
    assert "Traceback" not in caplog.text


def test_analyzer_llm_failure_uses_warning_not_exception_log(caplog):
    analyzer = Analyzer(LLMConfig(api_key="test-key"))

    def fail_call(prompt: str) -> str:
        raise RuntimeError("boom")

    analyzer._call_llm = fail_call

    with caplog.at_level(logging.WARNING, logger="src.pipeline.analyzer"):
        analyzed = analyzer.analyze_cluster(_cluster())

    assert analyzed.label == "Cluster 0"
    assert "LLM call failed" in analyzed.summary
    assert "Traceback" not in caplog.text


def test_analyzer_overall_prompt_formats_before_llm_fallback(caplog):
    analyzer = Analyzer(LLMConfig(api_key="test-key"))

    def fail_call(prompt: str) -> str:
        assert '"overall_insights"' in prompt
        raise RuntimeError("boom")

    analyzer._call_llm = fail_call

    with caplog.at_level(logging.WARNING, logger="src.pipeline.analyzer"):
        insights = analyzer.generate_overall_insights("Notion", [_cluster()])

    assert "LLM call failed" in insights["overall_insights"]
    assert "Traceback" not in caplog.text


def test_comparator_missing_key_uses_fallback_without_traceback(caplog):
    comparator = Comparator(LLMConfig(api_key=""))
    report = ProductReport(
        product="Notion",
        total_feedback_count=1,
        clusters=[_cluster()],
    )

    with caplog.at_level(logging.WARNING, logger="src.pipeline.comparator"):
        comparison = comparator.compare({"Notion": report})

    assert comparison.unique_pain_points == {"Notion": []}
    assert comparison.shared_pain_points == ["Cluster 0"]
    assert "LLM API key is not configured" in comparison.competitive_insights
    assert "Traceback" not in caplog.text


def test_comparator_prompt_formats_before_llm_fallback(caplog):
    comparator = Comparator(LLMConfig(api_key="test-key"))
    report = ProductReport(
        product="Notion",
        total_feedback_count=1,
        clusters=[_cluster()],
    )

    def fail_call(prompt: str) -> str:
        assert '"shared_pain_points"' in prompt
        raise RuntimeError("boom")

    comparator._call_llm = fail_call

    with caplog.at_level(logging.WARNING, logger="src.pipeline.comparator"):
        comparison = comparator.compare({"Notion": report})

    assert "LLM call failed" in comparison.competitive_insights
    assert "Traceback" not in caplog.text


def test_playwright_fallback_uses_thread_inside_asyncio_loop(monkeypatch):
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: None
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    fetcher = BrowserFetcher(RateLimiter(), use_playwright=True)
    calls = []

    def fake_thread_fetch(url, sync_playwright):
        calls.append(url)
        return HttpResponse(text="<html>ok</html>")

    monkeypatch.setattr(fetcher, "_fetch_playwright_in_thread", fake_thread_fetch)

    async def run_fetch():
        return fetcher.fetch_playwright("https://example.com")

    response = asyncio.run(run_fetch())

    assert response is not None
    assert response.text == "<html>ok</html>"
    assert calls == ["https://example.com"]
