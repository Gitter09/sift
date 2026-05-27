import asyncio
import logging
import sys
import types

import httpx
from openai import BadRequestError

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
        representative_quotes=[
            "Sync is unreliable and pages sometimes take a long time to load."
        ],
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


def test_analyzer_parses_markdown_fenced_json():
    analyzer = Analyzer(LLMConfig(api_key="test-key"))

    def call(prompt: str) -> str:
        return """```json
{
  "label": "Slow Sync",
  "summary": "Users report unreliable sync and slow page loading.",
  "severity": "high"
}
```"""

    analyzer._call_llm = call

    analyzed = analyzer.analyze_cluster(_cluster())

    assert analyzed.label == "Slow Sync"
    assert analyzed.summary == "Users report unreliable sync and slow page loading."
    assert analyzed.severity == "high"


def test_analyzer_parses_prose_wrapped_overall_json():
    analyzer = Analyzer(LLMConfig(api_key="test-key"))

    def call(prompt: str) -> str:
        return """Here is the JSON:
{
  "overall_insights": "The biggest weakness is reliability around sync and loading.",
  "top_pain_points": ["Slow Sync", "Page Load Latency", "Reliability Gaps"]
}
Hope this helps."""

    analyzer._call_llm = call

    cluster = _cluster()
    cluster.label = "Slow Sync"
    cluster.summary = "Users report unreliable sync and slow page loading."
    cluster.severity = "high"

    insights = analyzer.generate_overall_insights("Notion", [cluster])

    assert insights["overall_insights"].startswith("The biggest weakness")
    assert insights["top_pain_points"] == ["Slow Sync"]


def test_analyzer_invalid_severity_normalizes_to_medium():
    analyzer = Analyzer(LLMConfig(api_key="test-key"))

    def call(prompt: str) -> str:
        return """{
  "label": "Slow Sync",
  "summary": "Users report unreliable sync.",
  "severity": "critical"
}"""

    analyzer._call_llm = call

    analyzed = analyzer.analyze_cluster(_cluster())

    assert analyzed.severity == "medium"


def test_analyzer_repairs_invalid_json_once():
    analyzer = Analyzer(LLMConfig(api_key="test-key"))
    calls = []

    def call(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "label: Slow Sync, summary: Users report unreliable sync, severity: high"
        return """{
  "label": "Slow Sync",
  "summary": "Users report unreliable sync.",
  "severity": "high"
}"""

    analyzer._call_llm = call

    analyzed = analyzer.analyze_cluster(_cluster())

    assert analyzed.label == "Slow Sync"
    assert analyzed.severity == "high"
    assert len(calls) == 2


def test_analyzer_retries_oversized_max_tokens_bad_request():
    analyzer = Analyzer(LLMConfig(api_key="test-key", max_tokens=32000))
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                response = httpx.Response(
                    400,
                    request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
                )
                raise BadRequestError(
                    "max_tokens must be less than or equal to 8192",
                    response=response,
                    body={"error": {"message": "max_tokens is too large"}},
                )
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        finish_reason="stop",
                        message=types.SimpleNamespace(
                            content="""{
  "label": "Slow Sync",
  "summary": "Users report unreliable sync.",
  "severity": "high"
}"""
                        ),
                    )
                ]
            )

    analyzer.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )

    analyzed = analyzer.analyze_cluster(_cluster())

    assert analyzed.label == "Slow Sync"
    assert calls[0]["max_tokens"] == 32000
    assert calls[1]["max_tokens"] == 8000


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


def test_comparator_retries_unsupported_temperature_bad_request():
    comparator = Comparator(LLMConfig(api_key="test-key"))
    report = ProductReport(
        product="Notion",
        total_feedback_count=1,
        clusters=[_cluster()],
    )
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                response = httpx.Response(
                    400,
                    request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
                )
                raise BadRequestError(
                    "temperature is not supported for this model",
                    response=response,
                    body={"error": {"message": "Unsupported parameter: temperature"}},
                )
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(
                            content="""{
  "shared_pain_points": [],
  "unique_pain_points": {"Notion": ["Slow Sync"]},
  "competitive_insights": "Notion feedback centers on sync reliability."
}"""
                        )
                    )
                ]
            )

    comparator.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )

    comparison = comparator.compare({"Notion": report})

    assert comparison.unique_pain_points == {"Notion": ["Slow Sync"]}
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_comparator_preserves_exact_product_keys_from_wrapped_json():
    comparator = Comparator(LLMConfig(api_key="test-key"))
    report = ProductReport(
        product="Claude Code",
        total_feedback_count=1,
        clusters=[_cluster()],
    )

    def call(prompt: str) -> str:
        return """Sure:
{
  "shared_pain_points": [],
  "unique_pain_points": {
    "Claude Code": ["Terminal workflow friction"],
    "Not In Input": ["Should be ignored"]
  },
  "competitive_insights": "Claude Code feedback centers on workflow reliability."
}"""

    comparator._call_llm = call

    comparison = comparator.compare({"Claude Code": report})

    assert comparison.shared_pain_points == []
    assert comparison.unique_pain_points == {
        "Claude Code": ["Terminal workflow friction"]
    }
    assert comparison.competitive_insights.startswith("Claude Code feedback")


def test_comparator_invalid_response_falls_back_without_traceback(caplog):
    comparator = Comparator(LLMConfig(api_key="test-key"))
    report = ProductReport(
        product="Notion",
        total_feedback_count=1,
        clusters=[_cluster()],
    )

    def fail_repair(prompt: str) -> str:
        return ""

    comparator._call_llm = fail_repair

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
