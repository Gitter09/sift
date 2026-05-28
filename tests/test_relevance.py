from sift.config import ProductProfileConfig, RelevanceConfig, Settings
from sift.models import FeedbackItem
from sift.models import build_product_context
from sift.pipeline.relevance import RelevanceFilter


def _settings() -> Settings:
    return Settings(
        products={
            "Droid": ProductProfileConfig(
                aliases=["Factory Droid", "Droid coding agent"],
                negative_terms=["Android", "phone", "APK"],
                category="AI coding agent",
                description="Factory coding agent for software development",
                website="factory.ai",
                slugs=["droid"],
            ),
            "OpenCode": ProductProfileConfig(
                aliases=["opencode", "OpenCode coding agent"],
                negative_terms=["Anthropic pricing", "Claude pricing", "API prices"],
                category="AI coding agent",
                description="terminal coding agent for software development",
            ),
        },
        relevance=RelevanceConfig(enabled=True, threshold=0.45, min_items_before_relaxing=1),
    )


def test_droid_context_rejects_android_os_reviews():
    context = build_product_context("Droid", _settings())
    item = FeedbackItem(
        source="reddit",
        product="Droid",
        text="Android 15 broke notifications on my Droid phone after the APK update.",
    )

    kept, stats = RelevanceFilter(RelevanceConfig(threshold=0.45)).filter([item], context)

    assert kept == []
    assert stats.rejected == 1
    assert "Android" in item.metadata["negative_terms"]


def test_droid_context_accepts_factory_coding_agent_feedback():
    context = build_product_context("Droid", _settings())
    item = FeedbackItem(
        source="hacker_news",
        product="Droid",
        text="Factory Droid is impressive, but the coding agent gets stuck on larger software refactors.",
        url="https://www.factory.ai/droid",
    )

    kept, stats = RelevanceFilter(RelevanceConfig(threshold=0.45)).filter([item], context)

    assert kept == [item]
    assert stats.kept == 1
    assert item.metadata["relevance_score"] >= 0.45
    assert "Factory Droid" in item.metadata["matched_aliases"]


def test_opencode_context_rejects_provider_pricing_without_product_match():
    context = build_product_context("OpenCode", _settings())
    item = FeedbackItem(
        source="hacker_news",
        product="OpenCode",
        text="Anthropic pricing is going up again and Claude API prices make every coding workflow expensive.",
    )

    kept, stats = RelevanceFilter(RelevanceConfig(threshold=0.45)).filter([item], context)

    assert kept == []
    assert stats.rejected == 1
    assert "Anthropic pricing" in item.metadata["negative_terms"]


def test_metadata_alias_can_keep_story_comments():
    context = build_product_context("OpenCode", _settings())
    item = FeedbackItem(
        source="hacker_news",
        product="OpenCode",
        text="The terminal workflow is fast, but the install docs need work.",
        metadata={"story_title": "OpenCode coding agent launch thread"},
    )

    kept, stats = RelevanceFilter(RelevanceConfig(threshold=0.45)).filter([item], context)

    assert kept == [item]
    assert stats.kept == 1
    assert item.metadata["relevance_score"] >= 0.45
