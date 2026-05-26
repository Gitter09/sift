import logging
from typing import List, Optional
from src.scrapers.base import BaseScraper
from src.scrapers.reddit import RedditScraper
from src.scrapers.g2 import G2Scraper
from src.config import Settings
from src.scrapers.simple_sources import (
    AppStoreScraper,
    ChangelogScraper,
    DiscordExportsScraper,
    GitHubIssuesScraper,
    HackerNewsScraper,
    LinkedInCommentsScraper,
    PlayStoreScraper,
    ProductHuntScraper,
    SupportForumsScraper,
    YouTubeScraper,
)

logger = logging.getLogger(__name__)


AVAILABLE_SOURCES = {
    "reddit",
    "g2",
    "app_store",
    "play_store",
    "youtube",
    "hacker_news",
    "github_issues",
    "product_hunt",
    "support_forums",
    "changelogs",
    "discord_exports",
    "linkedin_comments",
}


def get_scraper(source: str, settings: Settings) -> Optional[BaseScraper]:
    if source in settings.sources.disabled_sources:
        logger.info("Source '%s' is disabled, skipping.", source)
        return None

    if source == "reddit":
        return RedditScraper(settings.reddit)
    elif source == "g2":
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
    for source in settings.sources.default_sources:
        scraper = get_scraper(source, settings)
        if scraper:
            scrapers.append(scraper)
    return scrapers


def default_sources(settings: Settings) -> List[str]:
    return [
        source
        for source in settings.sources.default_sources
        if source not in settings.sources.disabled_sources
    ]
