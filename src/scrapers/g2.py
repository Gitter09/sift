import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from datetime import datetime
from src.models.feedback import FeedbackItem
from src.scrapers.base import BaseScraper
from src.config import G2Config
from src.pipeline.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


class G2Scraper(BaseScraper):
    # G2 rate limiting context:
    #   - No official API, no published rate limits
    #   - Protected by Cloudflare (8/10 bypass difficulty) + Akamai (9/10 bypass difficulty)
    #   - ScrapeOps rates G2 9/10 overall scraping difficulty
    #   - Practical safe threshold: ~10-15 req/min with delays + UA rotation
    #   - Cloudflare triggers 429/403 if too many requests from same IP
    #   - Without delays, blocks happen within 20-30 requests

    def __init__(self, config: G2Config):
        self.config = config
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(
            max_requests_per_minute=config.max_requests_per_minute,
            jitter_range=config.jitter_range,
            backoff_base=config.backoff_base,
            max_backoff=config.max_backoff,
            max_retries=config.max_retries,
        )

    @property
    def source_name(self) -> str:
        return "g2"

    def _get_user_agent(self) -> str:
        if self.config.user_agent_rotation:
            return random.choice(USER_AGENTS)
        return USER_AGENTS[0]

    def _make_request(self, url: str, headers: dict) -> Optional[requests.Response]:
        """Make a request with rate limiting, exponential backoff on 429/403."""
        max_retries = self.config.max_retries
        for attempt in range(max_retries + 1):
            self.rate_limiter.wait()

            try:
                resp = self.session.get(url, headers=headers, timeout=15)
            except requests.RequestException as e:
                if self.rate_limiter.should_retry(attempt):
                    self.rate_limiter.backoff(attempt + 1, source="G2")
                    continue
                logger.error(
                    "G2 request failed after %d attempt(s): %s", attempt + 1, e,
                )
                return None

            if resp.status_code == 429:
                logger.warning(
                    "G2 rate limited (429) on attempt %d/%d. "
                    "G2's Cloudflare protection is throttling requests.",
                    attempt + 1, max_retries,
                )
                if self.rate_limiter.should_retry(attempt):
                    self.rate_limiter.backoff(attempt + 1, source="G2")
                    continue
                logger.error("G2 max retries exceeded for 429 on %s", url)
                return None

            if resp.status_code == 403:
                logger.warning(
                    "G2 blocked (403) on attempt %d/%d — likely Cloudflare/Akamai bot detection.",
                    attempt + 1, max_retries,
                )
                if self.rate_limiter.should_retry(attempt):
                    self.rate_limiter.backoff(attempt + 1, source="G2")
                    continue
                logger.error("G2 max retries exceeded for 403 on %s", url)
                return None

            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                if self.rate_limiter.should_retry(attempt):
                    self.rate_limiter.backoff(attempt + 1, source="G2")
                    continue
                logger.error(
                    "G2 HTTP error after %d attempt(s): %s", attempt + 1, e,
                )
                return None

            return resp

        return None

    def _get_product_url(self, product_name: str) -> Optional[str]:
        slug = product_name.lower().replace(" ", "-")
        search_url = f"https://www.g2.com/search?query={product_name}"
        headers = {"User-Agent": self._get_user_agent()}
        resp = self._make_request(search_url, headers)
        if not resp:
            logger.warning("G2 could not reach search page for '%s', guessing product URL", product_name)
            return f"https://www.g2.com/products/{slug}"

        soup = BeautifulSoup(resp.text, "html.parser")
        result_links = soup.select("a[href*='/products/']")
        if not result_links:
            return f"https://www.g2.com/products/{slug}"

        first_link = result_links[0]["href"]
        if not first_link.startswith("http"):
            first_link = f"https://www.g2.com{first_link}"
        return first_link

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        items: List[FeedbackItem] = []
        product_url = self._get_product_url(product_name)

        if not product_url:
            logger.warning("G2 could not find product page for '%s'", product_name)
            return items

        for page in range(1, self.config.max_pages + 1):
            url = f"{product_url}/reviews?page={page}"
            headers = {"User-Agent": self._get_user_agent()}

            resp = self._make_request(url, headers)
            if not resp:
                logger.warning("G2 failed to fetch page %d for '%s', stopping pagination", page, product_name)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            review_elements = soup.select("[class*='review']")

            if not review_elements:
                review_elements = soup.select("div[itemprop='review']")

            if not review_elements:
                logger.info("G2 no reviews found on page %d for '%s', stopping pagination", page, product_name)
                break

            for review_el in review_elements:
                text_el = review_el.select_one("[itemprop='reviewBody']")
                if not text_el:
                    text_el = review_el.select_one("p[class*='review']")
                if not text_el:
                    continue

                text = text_el.get_text(strip=True)
                if not text or len(text) < 20:
                    continue

                rating = None
                rating_el = review_el.select_one("[itemprop='ratingValue']")
                if rating_el:
                    try:
                        rating = float(rating_el.get("content", rating_el.get_text(strip=True)))
                    except (ValueError, TypeError):
                        pass

                if rating is None:
                    star_el = review_el.select_one("[class*='stars']")
                    if star_el:
                        star_classes = star_el.get("class", [])
                        for cls in star_classes:
                            match = re.search(r"stars-(\d)", cls)
                            if match:
                                rating = float(match.group(1))

                items.append(FeedbackItem(
                    source=self.source_name,
                    product=product_name,
                    text=text,
                    rating=rating,
                    url=url,
                    metadata={"page": page},
                ))

            if len(items) >= 50:
                break

        logger.info("G2: collected %d reviews for '%s'", len(items), product_name)
        return items
