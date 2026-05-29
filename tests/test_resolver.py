"""Unit tests for the resolver pipeline.

All I/O is mocked — these tests never touch the network or the user's
filesystem outside of pytest's tmp_path fixture.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from sift.pipeline.resolver import (
    ProductEnricher,
    ProductProfile,
    ResolverCache,
    ResolverPipeline,
    SourceRef,
)
from sift.pipeline.resolver.disambiguator import LLMDisambiguator, _extract_index
from sift.pipeline.resolver.models import ResolverCandidate, SearchHit
from sift.pipeline.resolver.search.base import SearchClient
from sift.pipeline.resolver.sources.product_hunt import ProductHuntResolver
from sift.pipeline.resolver.sources.g2 import G2Resolver
from sift.pipeline.resolver.sources.dev_to import DevToResolver
from sift.pipeline.resolver.sources.github_issues import GitHubIssuesResolver
from sift.pipeline.resolver.sources.play_store import PlayStoreResolver


# ---------- Test doubles ---------------------------------------------------


class FakeSearch(SearchClient):
    def __init__(self, hits_by_query: dict[str, List[SearchHit]] | None = None):
        self.hits_by_query = hits_by_query or {}
        self.calls: list[str] = []

    @property
    def backend_name(self) -> str:
        return "fake"

    def web_search(self, query: str, limit: int = 10) -> List[SearchHit]:
        self.calls.append(query)
        return list(self.hits_by_query.get(query, []))


def hit(url: str, title: str = "", snippet: str = "", rank: int = 1) -> SearchHit:
    return SearchHit(url=url, title=title, snippet=snippet, rank=rank)


# ---------- Cache ----------------------------------------------------------


def test_cache_roundtrip_profile_and_ref(tmp_path):
    cache = ResolverCache(str(tmp_path / "cache.db"), ttl_days=30)
    profile = ProductProfile(
        name="Notion", homepage="https://notion.so",
        description="workspace", category="productivity",
        search_snippets=["snippet a"], enricher_used="brave",
    )
    cache.put_profile(profile)
    fetched = cache.get_profile("Notion")
    assert fetched is not None
    assert fetched.value.homepage == "https://notion.so"
    assert fetched.resolver_used == "brave"

    ref = SourceRef(source="product_hunt", identifier="notion-2", confidence=0.9)
    cache.put_ref(profile, ref)
    fetched_ref = cache.get_ref("product_hunt", profile)
    assert fetched_ref is not None
    assert fetched_ref.value.identifier == "notion-2"


def test_cache_returns_none_for_unknown(tmp_path):
    cache = ResolverCache(str(tmp_path / "cache.db"))
    assert cache.get_profile("Unknown") is None


def test_cache_ttl_expiry(tmp_path):
    cache = ResolverCache(str(tmp_path / "cache.db"), ttl_days=30)
    profile = ProductProfile(name="Notion")
    cache.put_profile(profile)

    # Backdate the resolved_at directly in SQLite.
    stale = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with cache._connect() as conn:
        conn.execute("UPDATE profiles SET resolved_at = ?", (stale,))
    assert cache.get_profile("Notion") is None


def test_cache_clear_profile_cascades_to_refs(tmp_path):
    cache = ResolverCache(str(tmp_path / "cache.db"))
    profile = ProductProfile(name="Notion", homepage="https://notion.so")
    cache.put_profile(profile)
    cache.put_ref(profile, SourceRef(source="product_hunt", identifier="notion-2"))
    cache.put_ref(profile, SourceRef(source="g2", identifier="notion"))

    removed = cache.clear_profile("Notion")
    assert removed == 3  # 1 profile + 2 refs
    assert cache.get_profile("Notion") is None


# ---------- Enricher -------------------------------------------------------


def test_enricher_uses_hint_url_without_calling_search(tmp_path):
    search = FakeSearch()
    enricher = ProductEnricher(search)
    with patch.object(enricher._http, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            text=(
                '<html><head>'
                '<meta property="og:description" content="All-in-one workspace">'
                '<meta property="og:site_name" content="Notion">'
                '<meta property="og:type" content="website">'
                '</head></html>'
            ),
        )
        profile = enricher.enrich("Notion", hint_url="https://notion.so")

    assert search.calls == []  # hint short-circuits the search
    assert profile.homepage == "https://notion.so"
    assert profile.description == "All-in-one workspace"
    assert profile.site_name == "Notion"
    assert profile.enricher_used == "hint"


def test_enricher_picks_brand_domain_over_aggregators():
    search = FakeSearch({
        "Notion": [
            hit("https://en.wikipedia.org/wiki/Notion_(productivity_software)",
                "Notion (productivity software)", "an all-in-one workspace…", rank=1),
            hit("https://notion.so/", "Notion – Your connected workspace", "all-in-one…", rank=2),
            hit("https://producthunt.com/products/notion-2", "Notion on PH", "", rank=3),
        ]
    })
    enricher = ProductEnricher(search)
    with patch.object(enricher._http, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            text='<html><head><meta property="og:description" content="ws"></head></html>',
        )
        profile = enricher.enrich("Notion")
    assert profile.homepage == "https://notion.so"
    assert profile.enricher_used == "fake"
    assert "Notion" in profile.search_snippets[0]


def test_enricher_falls_back_to_snippets_when_homepage_missing():
    search = FakeSearch({
        "Frobnitz": [hit("https://aggregator.com/x", "Frobnitz", "developer api kit")]
    })
    enricher = ProductEnricher(search)
    with patch.object(enricher._http, "get") as mock_get:
        mock_get.return_value = None
        profile = enricher.enrich("Frobnitz")
    assert profile.category == "developer-tools"  # keyword-inferred


# ---------- Source resolvers ---------------------------------------------


def _profile(name: str = "Notion", category: str = "productivity") -> ProductProfile:
    return ProductProfile(
        name=name,
        homepage="https://notion.so",
        description="all-in-one workspace",
        category=category,
        search_snippets=["Notion – workspace and notes"],
    )


def test_product_hunt_resolver_extracts_slug():
    search = FakeSearch({
        'site:producthunt.com/products "Notion" productivity':
        [
            hit("https://www.producthunt.com/products/notion-2",
                "Notion on Product Hunt", "workspace", rank=1),
            hit("https://www.producthunt.com/products/notion",
                "Notion (sensor)", "home sensor", rank=2),
        ]
    })
    resolver = ProductHuntResolver(search_client=search)
    ref = resolver.resolve(_profile())
    assert ref is not None
    assert ref.identifier == "notion-2"
    assert ref.url.endswith("/products/notion-2")
    assert ref.confidence > 0


def test_g2_resolver_extracts_slug():
    search = FakeSearch({
        'site:g2.com/products "Notion" productivity':
        [
            hit("https://www.g2.com/products/notion/reviews",
                "Notion Reviews", "", rank=1),
        ]
    })
    resolver = G2Resolver(search_client=search)
    ref = resolver.resolve(_profile())
    assert ref is not None
    assert ref.identifier == "notion"
    assert ref.payload["reviews_url"].endswith("/reviews")


def test_dev_to_resolver_returns_tag_and_articles():
    search = FakeSearch({
        'site:dev.to/t "Notion"': [
            hit("https://dev.to/t/notion", "Notion tag", "notion posts", rank=1),
        ],
        'site:dev.to "Notion" productivity': [
            hit("https://dev.to/foo/notion-review-123", "review", "", rank=1),
            hit("https://dev.to/bar/notion-tips-456", "tips", "", rank=2),
        ],
    })
    resolver = DevToResolver(search_client=search)
    ref = resolver.resolve(_profile())
    assert ref is not None
    assert ref.identifier == "notion"
    assert len(ref.payload["article_urls"]) == 2


def test_github_resolver_picks_real_repo():
    search = FakeSearch({
        'site:github.com "Linear" productivity repository':
        [
            hit("https://github.com/sponsors/linear", "Sponsors", "", rank=1),
            hit("https://github.com/linear/linear", "linear/linear",
                "Linear official", rank=2),
        ]
    })
    resolver = GitHubIssuesResolver(search_client=search)
    ref = resolver.resolve(_profile(name="Linear"))
    assert ref is not None
    assert ref.identifier == "linear/linear"


def test_play_store_resolver_parses_package():
    search = FakeSearch({
        'site:play.google.com/store/apps "Notion" productivity':
        [
            hit(
                "https://play.google.com/store/apps/details?id=notion.id",
                "Notion app", "", rank=1,
            ),
        ]
    })
    resolver = PlayStoreResolver(search_client=search)
    ref = resolver.resolve(_profile())
    assert ref is not None
    assert ref.identifier == "notion.id"


def test_resolver_returns_none_when_no_search_results():
    resolver = ProductHuntResolver(search_client=FakeSearch())
    assert resolver.resolve(_profile()) is None


# ---------- Disambiguator -------------------------------------------------


def test_extract_index_handles_prose_around_json():
    assert _extract_index('Sure: {"index": 2, "reason": "best"}') == 2
    assert _extract_index('{"index": -1}') == -1
    assert _extract_index("nope") is None


def test_disambiguator_without_llm_picks_highest_score():
    candidates = [
        ResolverCandidate(ref=SourceRef(source="x", identifier="a"), raw_score=0.3),
        ResolverCandidate(ref=SourceRef(source="x", identifier="b"), raw_score=0.8),
    ]
    from sift.config import LLMConfig
    d = LLMDisambiguator(LLMConfig(api_key=""))
    picked = d.pick(_profile(), candidates)
    assert picked is not None
    assert picked.ref.identifier == "b"


def test_disambiguator_with_llm_respects_chosen_index():
    candidates = [
        ResolverCandidate(ref=SourceRef(source="x", identifier="a"), raw_score=0.9),
        ResolverCandidate(ref=SourceRef(source="x", identifier="b"), raw_score=0.1),
    ]
    from sift.config import LLMConfig
    d = LLMDisambiguator(LLMConfig(api_key="fake"))
    d.client = MagicMock()
    # Pretend the LLM picked candidate index 1 (which has lower raw_score).
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(
        message=MagicMock(content='{"index": 1, "reason": "better"}', reasoning_content=None),
        finish_reason="stop",
    )]
    with patch("sift.pipeline.resolver.disambiguator.create_chat_completion",
               return_value=mock_resp):
        picked = d.pick(_profile(), candidates)
    assert picked is not None
    assert picked.ref.identifier == "b"
    assert "llm" in picked.ref.resolver_used


# ---------- Pipeline -------------------------------------------------------


def test_pipeline_caches_profile_and_ref(tmp_path):
    search = FakeSearch({
        "Notion": [hit("https://notion.so", "Notion", "workspace", rank=1)],
        'site:producthunt.com/products "Notion" productivity':
        [hit("https://www.producthunt.com/products/notion-2", "PH", "", rank=1)],
    })
    enricher = ProductEnricher(search)
    with patch.object(enricher._http, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            text='<html><head><meta property="og:description" content="ws"></head></html>',
        )
        cache = ResolverCache(str(tmp_path / "cache.db"))
        resolvers = {"product_hunt": ProductHuntResolver(search_client=search)}
        pipeline = ResolverPipeline(cache, enricher, resolvers)

        first = pipeline.resolve("Notion", ["product_hunt"])
        assert first["product_hunt"].identifier == "notion-2"

        # Second call must be served from the cache — no extra search calls.
        calls_before = list(search.calls)
        second = pipeline.resolve("Notion", ["product_hunt"])
    assert second["product_hunt"].identifier == "notion-2"
    assert search.calls == calls_before


def test_pipeline_unknown_source_returns_none(tmp_path):
    cache = ResolverCache(str(tmp_path / "cache.db"))
    enricher = ProductEnricher(FakeSearch())
    pipeline = ResolverPipeline(cache, enricher, resolvers={})
    out = pipeline.resolve("X", ["bogus"], hint_url="https://example.com")
    assert out == {"bogus": None}


# ---------- Fix #1: app_store None-description ----------------------------


def test_app_store_resolver_tolerates_null_description():
    """iTunes JSON may carry `"description": null` (key present, value None);
    slicing must not raise."""
    from sift.pipeline.resolver.sources.app_store import AppStoreResolver

    resolver = AppStoreResolver(search_client=None, disambiguator=None)
    results = [
        {"trackId": 1, "trackName": "Notion", "sellerName": "Notion Labs",
         "trackViewUrl": "https://apps.apple.com/us/app/notion/id1232780281",
         "description": None, "bundleId": "notion.id"}
    ]
    candidates = resolver._collect(_profile(), results)
    assert len(candidates) == 1
    assert candidates[0].evidence_snippet == ""


# ---------- Fix #6: dev_to fallback tag preserves token order -------------


def test_dev_to_fallback_tag_preserves_token_order():
    """`Notion AI` must resolve to `notionai`, not the alphabetised `ainotion`."""
    search = FakeSearch()  # no Brave hits → fall through to synth tag
    resolver = DevToResolver(search_client=search, disambiguator=None)
    profile = ProductProfile(name="Notion AI", homepage="https://notion.so",
                             description="ai workspace", category="productivity")
    ref = resolver.resolve(profile)
    assert ref is not None
    assert ref.identifier == "notionai"
    assert ref.url == "https://dev.to/t/notionai"


# ---------- Fix #7: sitemap unwraps <sitemapindex> roots ------------------


def test_sitemap_unwraps_sitemapindex_root(tmp_path, monkeypatch):
    """A sitemap-of-sitemaps root must recurse into child shards rather than
    indexing the child URLs as fake products."""
    from sift.pipeline.resolver import sitemap as sitemap_mod
    from sift.pipeline.resolver.sitemap import SitemapIndex

    # Force-register a test host so we don't touch real URLs.
    monkeypatch.setitem(sitemap_mod._SITEMAP_URLS, "test.example",
                        ["https://test.example/root.xml"])

    index_xml = (
        b'<?xml version="1.0"?>'
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b'<sitemap><loc>https://test.example/shard1.xml</loc></sitemap>'
        b'<sitemap><loc>https://test.example/shard2.xml</loc></sitemap>'
        b'</sitemapindex>'
    )
    shard1_xml = (
        b'<?xml version="1.0"?>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b'<url><loc>https://test.example/p/widget-pro</loc></url>'
        b'</urlset>'
    )
    shard2_xml = (
        b'<?xml version="1.0"?>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b'<url><loc>https://test.example/p/gizmo-2</loc></url>'
        b'</urlset>'
    )
    responses = {
        "https://test.example/root.xml": shard1_xml.replace(b"urlset", b"sitemapindex").replace(
            b"<url><loc>https://test.example/p/widget-pro</loc></url>",
            b"<sitemap><loc>https://test.example/shard1.xml</loc></sitemap>"
            b"<sitemap><loc>https://test.example/shard2.xml</loc></sitemap>",
        ),
        "https://test.example/shard1.xml": shard1_xml,
        "https://test.example/shard2.xml": shard2_xml,
    }
    responses["https://test.example/root.xml"] = index_xml

    def fake_get(url, timeout=30):
        body = responses[url]
        return MagicMock(status_code=200, content=body)

    sitemap = SitemapIndex(str(tmp_path / "sitemap.db"))
    with patch.object(sitemap._http, "get", side_effect=fake_get):
        hits = sitemap.web_search("site:test.example widget", limit=10)

    slugs = {h.title for h in hits}
    # Child sitemap URLs must NOT have leaked in as products.
    assert "shard1.xml" not in slugs
    assert "shard2.xml" not in slugs
    # The real product slug from the shard is reachable.
    assert "widget-pro" in slugs


# ---------- Fix #8: clear_profile/clear_ref bypass TTL --------------------


def test_clear_profile_removes_refs_when_profile_is_stale(tmp_path):
    """`clear_profile` must purge orphan ref rows even when the profile has
    aged past the cache TTL."""
    cache = ResolverCache(str(tmp_path / "cache.db"), ttl_days=30)
    profile = ProductProfile(name="Stale", homepage="https://stale.example")
    cache.put_profile(profile)
    cache.put_ref(profile, SourceRef(source="product_hunt", identifier="stale-2"))
    cache.put_ref(profile, SourceRef(source="g2", identifier="stale"))

    # Backdate the profile past the TTL.
    expired = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with cache._connect() as conn:
        conn.execute("UPDATE profiles SET resolved_at = ?", (expired,))
    assert cache.get_profile("Stale") is None  # confirm TTL expiry

    removed = cache.clear_profile("Stale")
    assert removed == 3  # 1 profile + 2 refs

    # Inspect the table directly to be sure no orphans remain.
    with cache._connect() as conn:
        ref_count = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
    assert ref_count == 0


def test_clear_ref_works_on_stale_profile(tmp_path):
    cache = ResolverCache(str(tmp_path / "cache.db"), ttl_days=30)
    profile = ProductProfile(name="Stale", homepage="https://stale.example")
    cache.put_profile(profile)
    cache.put_ref(profile, SourceRef(source="g2", identifier="stale"))

    with cache._connect() as conn:
        conn.execute(
            "UPDATE profiles SET resolved_at = ?",
            ((datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),),
        )

    assert cache.clear_ref("Stale", "g2") == 1


# ---------- Fix #9: disambiguator caps max_tokens -------------------------


def test_disambiguator_caps_max_tokens_below_config_value():
    """A configured llm.max_tokens of 8000 must not propagate into the
    disambiguator call — its reply is a single-line JSON object."""
    from sift.config import LLMConfig

    config = LLMConfig(api_key="sk-test", base_url="https://example",
                       model="gpt-4o", max_tokens=8000)
    d = LLMDisambiguator(config)
    d.client = MagicMock()  # treat as available

    captured: dict = {}

    def fake_completion(client, model, messages, options, log):
        captured["max_tokens"] = options.max_tokens
        msg = MagicMock()
        msg.message.content = '{"index": 0, "reason": "ok"}'
        msg.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [msg]
        return resp

    candidates = [
        ResolverCandidate(
            ref=SourceRef(source="x", identifier=str(i)),
            evidence_title=f"c{i}",
            evidence_snippet="",
            raw_score=0.5,
        )
        for i in range(2)
    ]
    with patch(
        "sift.pipeline.resolver.disambiguator.create_chat_completion",
        side_effect=fake_completion,
    ):
        d.pick(_profile(), candidates)

    assert captured["max_tokens"] == 512
