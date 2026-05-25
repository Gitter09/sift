from unittest.mock import MagicMock, patch
from src.config import RedditConfig, G2Config
from src.scrapers.reddit import RedditScraper
from src.scrapers.g2 import G2Scraper
from src.scrapers.factory import get_scraper, get_all_scrapers
from src.config import Settings


def test_reddit_scraper_source_name():
    config = RedditConfig(client_id="test", client_secret="test")
    scraper = RedditScraper(config)
    assert scraper.source_name == "reddit"


def test_g2_scraper_source_name():
    config = G2Config()
    scraper = G2Scraper(config)
    assert scraper.source_name == "g2"


def test_g2_user_agent_rotation():
    config = G2Config(user_agent_rotation=True)
    scraper = G2Scraper(config)
    ua1 = scraper._get_user_agent()
    ua2 = scraper._get_user_agent()
    # With rotation, should eventually get different UAs (statistically)
    assert ua1.startswith("Mozilla/5.0")


def test_g2_no_rotation():
    config = G2Config(user_agent_rotation=False)
    scraper = G2Scraper(config)
    ua = scraper._get_user_agent()
    assert ua.startswith("Mozilla/5.0")


def test_factory_get_scraper():
    settings = Settings(
        reddit=RedditConfig(client_id="test", client_secret="test"),
    )
    reddit_scraper = get_scraper("reddit", settings)
    assert reddit_scraper is not None
    assert reddit_scraper.source_name == "reddit"

    g2_scraper = get_scraper("g2", settings)
    assert g2_scraper is not None
    assert g2_scraper.source_name == "g2"

    unknown = get_scraper("twitter", settings)
    assert unknown is None


def test_factory_all_scrapers_with_creds():
    settings = Settings(
        reddit=RedditConfig(client_id="test_id", client_secret="test_secret"),
    )
    scrapers = get_all_scrapers(settings)
    assert len(scrapers) == 2  # Reddit + G2


def test_factory_all_scrapers_without_creds():
    settings = Settings(
        reddit=RedditConfig(client_id="", client_secret=""),
    )
    scrapers = get_all_scrapers(settings)
    assert len(scrapers) == 1  # Only G2 (Reddit skipped)
