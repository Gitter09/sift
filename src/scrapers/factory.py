from typing import List, Optional
from src.scrapers.base import BaseScraper
from src.scrapers.reddit import RedditScraper
from src.scrapers.g2 import G2Scraper
from src.config import Settings


def get_scraper(source: str, settings: Settings) -> Optional[BaseScraper]:
    if source == "reddit":
        return RedditScraper(settings.reddit)
    elif source == "g2":
        return G2Scraper(settings.g2)
    return None


def get_all_scrapers(settings: Settings) -> List[BaseScraper]:
    scrapers: List[BaseScraper] = []
    if settings.reddit.client_id and settings.reddit.client_secret:
        scrapers.append(RedditScraper(settings.reddit))
    else:
        print("[Config] Reddit credentials not set, skipping Reddit scraper")
    scrapers.append(G2Scraper(settings.g2))
    return scrapers
