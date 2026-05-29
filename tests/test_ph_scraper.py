"""Tests for the ProductHunt scraper rewrite + JsonExportScraper session reuse.

Covers code-review fixes #2 (search fallback), #3 (HTML name-relevance
filter), #5 (transient-error classification), and #10 (JsonExportScraper
must inherit RequestsScraper for shared rate-limit / session).
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sift.config import (
    DiscordExportsConfig,
    LinkedInCommentsConfig,
    ProductHuntConfig,
)
from sift.scrapers.simple_sources import (
    DiscordExportsScraper,
    JsonExportScraper,
    LinkedInCommentsScraper,
    ProductHuntScraper,
    RequestsScraper,
    _PHTransientError,
    _walk_ph_feedback,
)


def _ph_config(**overrides) -> ProductHuntConfig:
    base = dict(
        slugs={},
        max_items=50,
        request_delay=0.0,
        max_requests_per_minute=60,
        use_playwright_fallback=False,
        client_id="cid",
        client_secret="csec",
    )
    base.update(overrides)
    return ProductHuntConfig(**base)


# ---------------------------------------------------------------------------
# Fix #2: PH API surfaces actionable hint when the slug guess misses
# ---------------------------------------------------------------------------
# PH v2 schema does NOT expose `posts(search:)` — see ARCHITECTURE.md
# Decision 042. So when the guessed slug returns null we cannot fall back
# to a name search; the fix is to log a clear, user-actionable message
# telling them to configure a slug (or enable the resolver) instead of
# emitting a misleading info-level "no post found" line that hides the
# real cause.


def test_ph_api_logs_actionable_hint_when_slug_guess_misses():
    """A guessed slug that returns no post must produce a warning that
    points at the resolver / manual config — not a silent info log."""
    scraper = ProductHuntScraper(_ph_config())
    scraper._access_token = "tok"

    def fake_post(payload, token):
        return {"data": {"post": None}}  # PH has no such post

    with patch.object(scraper, "_post_ph_graphql", side_effect=fake_post), \
         patch("sift.scrapers.simple_sources.logger") as mock_logger:
        items = scraper._scrape_via_api("GitHub Copilot")

    assert items == []
    # The warning must mention the configuration path so the user can fix it.
    warning_messages = [str(call) for call in mock_logger.warning.call_args_list]
    assert any("product_hunt.slugs" in m for m in warning_messages)
    assert any("resolver" in m for m in warning_messages)


def test_ph_api_confirmed_slug_uses_info_log_not_warning():
    """If the resolver / user config provided the slug (via source_ref or
    config.slugs), a null PH response is authoritative — log as info, not
    a warning that re-suggests configuring something already configured."""
    scraper = ProductHuntScraper(_ph_config())
    scraper._access_token = "tok"

    # Simulate a SourceRef coming from the resolver.
    ref = MagicMock()
    ref.identifier = "confirmed-slug"
    scraper.source_ref = ref

    def fake_post(payload, token):
        return {"data": {"post": None}}

    with patch.object(scraper, "_post_ph_graphql", side_effect=fake_post), \
         patch("sift.scrapers.simple_sources.logger") as mock_logger:
        items = scraper._scrape_via_api("Confirmed Slug")

    assert items == []
    # Info-level (not a warning, because nothing to action).
    info_messages = [str(call) for call in mock_logger.info.call_args_list]
    warning_messages = [str(call) for call in mock_logger.warning.call_args_list]
    assert any("no post found" in m for m in info_messages)
    assert not any("product_hunt.slugs" in m for m in warning_messages)


# ---------------------------------------------------------------------------
# Fix #5: _post_ph_graphql distinguishes transient errors
# ---------------------------------------------------------------------------


def test_ph_api_transient_error_returns_empty_with_warning():
    """A transient HTTP failure must produce a warning and an empty list —
    not a misleading 'no post found' log."""
    scraper = ProductHuntScraper(_ph_config())
    scraper._access_token = "tok"

    def boom(payload, token):
        raise _PHTransientError("Product Hunt GraphQL HTTP 503: down")

    # Patch the module-level logger directly — caplog gets clobbered when
    # the full suite reconfigures logging.
    with patch.object(scraper, "_post_ph_graphql", side_effect=boom), \
         patch("sift.scrapers.simple_sources.logger") as mock_logger:
        items = scraper._scrape_via_api("Notion")

    assert items == []
    warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
    info_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert any("503" in c or "GraphQL" in c for c in warning_calls)
    # And the misleading info message must NOT have been emitted.
    assert not any("no post found" in c for c in info_calls)


def test_post_ph_graphql_raises_on_network_failure():
    """The lower-level helper must raise _PHTransientError so callers can
    log the right thing — not return {} silently."""
    scraper = ProductHuntScraper(_ph_config())
    scraper._access_token = "tok"

    # Force the underlying POST to raise.
    fake_session = MagicMock()
    fake_session.post.side_effect = ConnectionError("connection reset")
    scraper._curl_session = MagicMock(_session=fake_session)

    with pytest.raises(_PHTransientError):
        scraper._post_ph_graphql({"query": "x"}, "tok")


# ---------------------------------------------------------------------------
# Fix #3: PH HTML walker filters by product-name relevance
# ---------------------------------------------------------------------------


def test_walk_ph_feedback_yields_unfiltered_nodes():
    """_walk_ph_feedback itself does NOT filter by product name — the caller
    is responsible (so this test pins the helper's behaviour; the relevance
    filter is checked end-to-end in the next test)."""
    payload = {
        "data": {
            "comments": [
                {"id": "1", "__typename": "Comment", "body": "A long enough comment about Notion that mentions it."},
                {"id": "2", "__typename": "Comment", "body": "A long enough comment about Coda that does not."},
            ]
        }
    }
    texts = [t for t, _, _ in _walk_ph_feedback(payload, "notion")]
    # Both nodes look like feedback to the walker.
    assert len(texts) == 2


def test_scrape_via_html_filters_off_topic_comments():
    """After the walker yields candidates, _scrape_via_html must drop
    nodes that don't mention the product — prevents cross-product
    pollution when the slug guess lands on the wrong page."""
    scraper = ProductHuntScraper(_ph_config())

    next_data = {
        "props": {
            "pageProps": {
                "comments": [
                    {"id": "1", "__typename": "Comment",
                     "body": "Notion has been great for our team's documentation."},
                    {"id": "2", "__typename": "Comment",
                     "body": "Coda is what we ended up switching to for the same reason."},
                ]
            }
        }
    }

    soup = MagicMock()
    soup.title.string = "Notion - Product Hunt"
    soup.find.return_value = None  # no Cloudflare challenge

    with patch.object(scraper, "_get_html", return_value=soup), \
         patch.object(scraper, "_extract_next_data", return_value=next_data):
        items = scraper._scrape_via_html("Notion")

    bodies = [item.text for item in items]
    assert any("Notion" in b for b in bodies), "must keep the on-topic comment"
    assert not any("Coda" in b for b in bodies), "must drop the off-topic comment"


# ---------------------------------------------------------------------------
# Fix #10: JsonExportScraper inherits RequestsScraper for shared session
# ---------------------------------------------------------------------------


def test_discord_exports_scraper_inherits_requests_scraper():
    """DiscordExportsScraper must go through the shared rate-limited
    curl_cffi session — not the bare curl_requests.get."""
    config = DiscordExportsConfig(paths=[], urls=[], max_items=50)
    scraper = DiscordExportsScraper(config)
    assert isinstance(scraper, RequestsScraper)
    assert hasattr(scraper, "rate_limiter")
    assert hasattr(scraper, "_curl_session")


def test_linkedin_comments_scraper_inherits_requests_scraper():
    config = LinkedInCommentsConfig(paths=[], urls=[], max_items=50)
    scraper = LinkedInCommentsScraper(config)
    assert isinstance(scraper, RequestsScraper)


def test_json_export_url_fetch_routes_through_shared_get_json():
    """The URL leg must call self._get_json (which rate-limits and reuses
    the session) rather than a bare curl_requests.get."""
    config = DiscordExportsConfig(
        paths=[], urls=["https://example/messages.json"], max_items=10,
    )
    scraper = DiscordExportsScraper(config)

    sample = [{
        "content": "User reported a bug in the Notion sync today and asked for a fix.",
    }]
    with patch.object(scraper, "_get_json", return_value=sample) as mock_get:
        items = scraper.scrape("Notion")

    mock_get.assert_called_once_with("https://example/messages.json")
    assert len(items) == 1
    assert items[0].text.startswith("User reported")
