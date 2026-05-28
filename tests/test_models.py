import json
import hashlib
from datetime import datetime
from sift.models import (
    ClusterResult,
    ComparisonReport,
    FeedbackItem,
    ProductReport,
)


def test_feedback_item_to_dict():
    item = FeedbackItem(
        source="reddit",
        product="Notion",
        text="Notion is slow and buggy",
        rating=None,
        url="https://reddit.com/r/test/123",
        date=datetime(2025, 1, 1),
        metadata={"subreddit": "SaaS", "score": 5},
    )
    d = item.to_dict()
    assert d["source"] == "reddit"
    assert d["product"] == "Notion"
    assert d["text"] == "Notion is slow and buggy"
    assert d["metadata"]["subreddit"] == "SaaS"
    assert "author" not in d  # author is stripped for anonymity
    assert "id" in d
    assert len(d["id"]) == 16


def test_feedback_item_id_deterministic():
    """Same source + URL should produce the same ID."""
    item1 = FeedbackItem(
        source="reddit", product="Notion", text="test",
        url="https://reddit.com/r/test/1",
    )
    item2 = FeedbackItem(
        source="reddit", product="Notion", text="different text, same URL",
        url="https://reddit.com/r/test/1",
    )
    assert item1.id == item2.id


def test_feedback_item_id_different():
    """Different URLs should produce different IDs."""
    item1 = FeedbackItem(
        source="reddit", product="Notion", text="same text",
        url="https://reddit.com/r/test/1",
    )
    item2 = FeedbackItem(
        source="reddit", product="Notion", text="same text",
        url="https://reddit.com/r/test/2",
    )
    assert item1.id != item2.id


def test_feedback_item_id_no_url_fallback():
    """When no URL, ID falls back to hashing the text."""
    item = FeedbackItem(
        source="g2", product="Notion", text="Some review text",
    )
    assert len(item.id) == 16
    # Should not crash
    assert isinstance(item.id, str)


def test_cluster_result():
    items = [
        FeedbackItem(source="g2", product="Notion", text="Slow loading"),
        FeedbackItem(source="g2", product="Notion", text="Takes forever to sync"),
        FeedbackItem(source="g2", product="Notion", text="Crashes on large pages"),
    ]
    cluster = ClusterResult(
        cluster_id=0,
        label="Performance Issues",
        items=items,
        summary="Users complain about speed",
        severity="high",
        representative_quotes=["Slow loading", "Takes forever to sync", "Crashes on large pages"],
    )
    assert cluster.size == 3
    assert not cluster.is_noise
    d = cluster.to_dict()
    assert d["label"] == "Performance Issues"
    assert d["size"] == 3


def test_cluster_noise():
    noise = ClusterResult(cluster_id=-1, items=[FeedbackItem(source="g2", product="Notion", text="random")])
    assert noise.is_noise


def test_product_report():
    cluster = ClusterResult(
        cluster_id=0,
        label="Slow",
        items=[FeedbackItem(source="g2", product="Notion", text="slow")],
        summary="Too slow",
        severity="high",
    )
    report = ProductReport(
        product="Notion",
        total_feedback_count=10,
        clusters=[cluster],
        overall_insights="Notion has performance issues",
        top_pain_points=["Performance", "Price"],
    )
    d = report.to_dict()
    assert d["product"] == "Notion"
    assert d["total_feedback_count"] == 10
    assert len(d["clusters"]) == 1


def test_comparison_report():
    report1 = ProductReport(product="Notion", total_feedback_count=5, top_pain_points=["Speed"])
    report2 = ProductReport(product="Obsidian", total_feedback_count=5, top_pain_points=["Sync"])
    comp = ComparisonReport(
        products=["Notion", "Obsidian"],
        product_reports={"Notion": report1, "Obsidian": report2},
        shared_pain_points=["Learning curve"],
        unique_pain_points={"Notion": ["Speed"], "Obsidian": ["Sync"]},
        competitive_insights="Obsidian is faster locally but Notion has better collaboration",
    )
    d = comp.to_dict()
    assert "Notion" in d["product_reports"]
    assert "Learning curve" in d["shared_pain_points"]
