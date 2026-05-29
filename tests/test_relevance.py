"""Layer 1 (heuristic scorer) tests for the content disambiguator.

RelevanceFilter no longer makes the final keep/reject call — it scores items and
``prefilter`` drops only sub-``heuristic_hard_reject`` garbage. The semantic
keep/reject decision belongs to ContentDisambiguator (Layers 2 + 3), tested in
test_disambiguator.py.
"""

from sift.config import DisambiguatorConfig, ProductProfileConfig, Settings
from sift.models import FeedbackItem, build_product_context
from sift.pipeline.relevance import RelevanceFilter
from sift.pipeline.ambiguous_words import is_ambiguous_name


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
                negative_terms=["Anthropic pricing", "Claude pricing"],
                category="AI coding agent",
                description="terminal coding agent for software development",
            ),
            "Notion": ProductProfileConfig(
                aliases=["Notion app"],
                category="productivity workspace",
                description="notes and docs productivity workspace",
                website="notion.so",
            ),
        },
    )


def _filter() -> RelevanceFilter:
    return RelevanceFilter(DisambiguatorConfig())


def test_clear_product_feedback_scores_high_and_survives():
    context = build_product_context("Droid", _settings())
    item = FeedbackItem(
        source="hacker_news",
        product="Droid",
        text="Factory Droid is impressive, but the coding agent gets stuck on larger software refactors.",
        url="https://www.factory.ai/droid",
    )

    kept, stats = _filter().prefilter([item], context)

    assert kept == [item]
    assert stats.dropped == 0
    assert item.metadata["relevance_score"] >= 0.5
    assert "Factory Droid" in item.metadata["matched_aliases"]


def test_negative_terms_drop_off_context_item():
    context = build_product_context("Droid", _settings())
    item = FeedbackItem(
        source="reddit",
        product="Droid",
        text="Android 15 broke notifications on my Droid phone after the APK update.",
    )

    kept, stats = _filter().prefilter([item], context)

    assert kept == []
    assert stats.dropped == 1
    assert "Android" in item.metadata["negative_terms"]


def test_ambiguous_auto_negative_penalizes_common_word_usage():
    context = build_product_context("Notion", _settings())
    assert is_ambiguous_name(context.canonical_name)
    item = FeedbackItem(
        source="hacker_news",
        product="Notion",
        text="I have no notion of how this works; the notion of shared state is confusing.",
    )

    kept, stats = _filter().prefilter([item], context)

    # "the notion of" is a common-word construction, not the product.
    assert kept == []
    assert "the notion of" in item.metadata.get("auto_negative_patterns", [])


def test_ambiguous_body_only_alias_gets_reduced_weight():
    f = _filter()
    context = build_product_context("Notion", _settings())

    body_only = FeedbackItem(source="reddit", product="Notion", text="I switched to Notion last week.")
    structural = FeedbackItem(
        source="reddit",
        product="Notion",
        text="I switched to Notion last week.",
        url="https://notion.so/blog",
        metadata={"title": "Notion app review"},
    )

    f.score(body_only, context, ambiguous=True)
    f.score(structural, context, ambiguous=True)

    # Structural (URL/title) mention is stronger evidence than body-only prose.
    assert structural.metadata["relevance_score"] > body_only.metadata["relevance_score"]


def test_dev_source_bonus_for_dev_tool_category():
    f = _filter()
    context = build_product_context("OpenCode", _settings())
    text = "opencode keeps crashing on large repos."

    dev = FeedbackItem(source="github_issues", product="OpenCode", text=text)
    general = FeedbackItem(source="reddit", product="OpenCode", text=text)

    f.score(dev, context, ambiguous=False)
    f.score(general, context, ambiguous=False)

    assert dev.metadata["relevance_score"] > general.metadata["relevance_score"]
    assert any(r.startswith("source_type:") for r in dev.metadata["relevance_reasons"])


def test_disabled_config_passes_everything_through():
    context = build_product_context("Droid", _settings())
    items = [FeedbackItem(source="reddit", product="Droid", text="totally unrelated text")]

    f = RelevanceFilter(DisambiguatorConfig(enabled=False))
    kept, stats = f.prefilter(items, context)

    assert kept == items
    assert stats.dropped == 0
