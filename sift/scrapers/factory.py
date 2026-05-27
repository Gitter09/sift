import logging
from typing import List, Optional
from sift.scrapers.base import BaseScraper
from sift.scrapers.reddit import RedditScraper
from sift.scrapers.g2 import G2Scraper
from sift.config import Settings
from sift.scrapers.simple_sources import (
    AppStoreScraper,
    ChangelogScraper,
    DevToScraper,
    DiscordExportsScraper,
    GitHubIssuesScraper,
    HackerNewsScraper,
    LinkedInCommentsScraper,
    PlayStoreScraper,
    ProductHuntScraper,
    StackOverflowScraper,
    SupportForumsScraper,
    YouTubeScraper,
)

logger = logging.getLogger(__name__)

_g2_proxy_warning_shown = False

AVAILABLE_SOURCES = {
    "reddit",
    "g2",
    "app_store",
    "play_store",
    "youtube",
    "hacker_news",
    "github_issues",
    "product_hunt",
    "stack_overflow",
    "dev_to",
    "support_forums",
    "changelogs",
    "discord_exports",
    "linkedin_comments",
}


def get_scraper(source: str, settings: Settings) -> Optional[BaseScraper]:
    global _g2_proxy_warning_shown
    if source in settings.sources.disabled_sources:
        logger.info("Source '%s' is disabled, skipping.", source)
        return None

    if source == "reddit":
        return RedditScraper(settings.reddit)
    elif source == "g2":
        if not settings.g2.proxy_url and not _g2_proxy_warning_shown:
            from sift.ui.display import print_g2_proxy_warning
            print_g2_proxy_warning()
            _g2_proxy_warning_shown = True
        return G2Scraper(settings.g2)
    elif source == "app_store":
        return AppStoreScraper(settings.app_store)
    elif source == "play_store":
        return PlayStoreScraper(settings.play_store)
    elif source == "youtube":
        return YouTubeScraper(settings.youtube)
    elif source == "hacker_news":
        return HackerNewsScraper(settings.hacker_news)
    elif source == "github_issues":
        return GitHubIssuesScraper(settings.github_issues)
    elif source == "product_hunt":
        return ProductHuntScraper(settings.product_hunt)
    elif source == "stack_overflow":
        return StackOverflowScraper(settings.stack_overflow)
    elif source == "dev_to":
        return DevToScraper(settings.dev_to)
    elif source == "support_forums":
        return SupportForumsScraper(settings.support_forums)
    elif source == "changelogs":
        return ChangelogScraper(settings.changelogs)
    elif source == "discord_exports":
        return DiscordExportsScraper(settings.discord_exports)
    elif source == "linkedin_comments":
        return LinkedInCommentsScraper(settings.linkedin_comments)
    return None


def get_all_scrapers(settings: Settings) -> List[BaseScraper]:
    scrapers: List[BaseScraper] = []
    for source in default_sources(settings):
        scraper = get_scraper(source, settings)
        if scraper:
            scrapers.append(scraper)
    return scrapers


def default_sources(settings: Settings) -> List[str]:
    return [
        source
        for source in settings.sources.default_sources
        if source not in settings.sources.disabled_sources
        and is_source_configured(source, settings)
    ]


def is_source_configured(source: str, settings: Settings) -> bool:
    if source == "reddit":
        return bool(settings.reddit.client_id and settings.reddit.client_secret)
    if source == "app_store":
        return bool(settings.app_store.app_ids)
    if source == "play_store":
        return bool(settings.play_store.package_names)
    if source == "youtube":
        return bool(settings.youtube.api_key and settings.youtube.video_ids)
    if source == "support_forums":
        return bool(settings.support_forums.search_urls)
    if source == "changelogs":
        return bool(settings.changelogs.urls or settings.changelogs.search_urls)
    if source == "discord_exports":
        return bool(settings.discord_exports.paths or settings.discord_exports.urls)
    if source == "linkedin_comments":
        return bool(settings.linkedin_comments.paths or settings.linkedin_comments.urls)
    if source == "g2":
        return bool(settings.g2.proxy_url)
    # These sources work without any configuration (auto-discover or open APIs)
    return source in {"hacker_news", "github_issues", "product_hunt", "stack_overflow", "dev_to"}
