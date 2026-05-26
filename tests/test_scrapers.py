from src.config import RedditConfig, G2Config, SourcesConfig
from src.scrapers.reddit import RedditScraper
from src.scrapers.g2 import G2Scraper
from src.scrapers.factory import default_sources, get_scraper, get_all_scrapers
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
    config = G2Config(user_agent_rotation=True, use_playwright_fallback=True)
    scraper = G2Scraper(config)
    assert scraper.config.use_playwright_fallback is True
    assert scraper.source_name == "g2"


def test_g2_no_rotation():
    config = G2Config(user_agent_rotation=False, use_playwright_fallback=False)
    scraper = G2Scraper(config)
    assert scraper.config.use_playwright_fallback is False
    assert scraper.source_name == "g2"


def test_factory_get_scraper():
    settings = Settings(
        sources=SourcesConfig(disabled_sources=[]),
        reddit=RedditConfig(client_id="test", client_secret="test"),
    )
    reddit_scraper = get_scraper("reddit", settings)
    assert reddit_scraper is not None
    assert reddit_scraper.source_name == "reddit"

    g2_scraper = get_scraper("g2", settings)
    assert g2_scraper is not None
    assert g2_scraper.source_name == "g2"

    hacker_news_scraper = get_scraper("hacker_news", settings)
    assert hacker_news_scraper is not None
    assert hacker_news_scraper.source_name == "hacker_news"

    unknown = get_scraper("twitter", settings)
    assert unknown is None


def test_factory_reddit_is_muted_by_default_even_with_creds():
    settings = Settings(
        reddit=RedditConfig(client_id="test_id", client_secret="test_secret"),
    )
    assert get_scraper("reddit", settings) is None


def test_factory_all_scrapers_uses_default_non_reddit_sources():
    settings = Settings()
    scrapers = get_all_scrapers(settings)
    names = [scraper.source_name for scraper in scrapers]
    assert "reddit" not in names
    assert names == default_sources(settings)


def test_factory_can_reactivate_reddit_when_enabled():
    settings = Settings(
        sources=SourcesConfig(default_sources=["reddit", "g2"], disabled_sources=[]),
        reddit=RedditConfig(client_id="test_id", client_secret="test_secret"),
    )
    scrapers = get_all_scrapers(settings)
    assert [scraper.source_name for scraper in scrapers] == ["reddit", "g2"]
