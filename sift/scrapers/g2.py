import re
import logging
from typing import List, Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from sift.config import G2Config
from sift.models import FeedbackItem
from sift.pipeline.http_client import (
    CurlCffiSession,
    BrowserFetcher,
    HttpResponse,
)
from sift.pipeline.rate_limiter import RateLimiter
from sift.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Chrome 124 on macOS — matches the TLS fingerprint we impersonate
_G2_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class G2Scraper(BaseScraper):
    """Scrape G2 reviews.

    Uses a two-tier anti-bot strategy:

    * **Tier 1**: ``curl_cffi`` with Chrome 124 TLS fingerprint impersonation.
    * **Tier 2**: Playwright (real Chromium browser) fallback on 403 blocks.
    """

    def __init__(self, config: G2Config):
        self.config = config
        self._curl_session = CurlCffiSession()
        self.rate_limiter = RateLimiter(
            max_requests_per_minute=config.max_requests_per_minute,
            jitter_range=config.jitter_range,
            backoff_base=config.backoff_base,
            max_backoff=config.max_backoff,
            max_retries=config.max_retries,
        )
        self._browser_fetcher = BrowserFetcher(
            self.rate_limiter,
            use_playwright=config.use_playwright_fallback,
        )

    @property
    def source_name(self) -> str:
        return "g2"

    def _make_request(
        self, url: str, headers: dict | None = None
    ) -> Optional[curl_requests.Response | HttpResponse]:
        """Make a request with two-tier anti-bot strategy.

        Tier 1: curl_cffi with Chrome TLS impersonation.
        Tier 2: Playwright (real Chromium) fallback on 403.
        """
        max_retries = self.config.max_retries
        total_attempts = max_retries + 1  # e.g. 3 retries = 4 total attempts

        for attempt in range(total_attempts):
            self.rate_limiter.wait()

            # --- Tier 1: curl_cffi (with optional proxy) ------------------
            proxy = self.config.proxy_url or None
            proxies = {"https": proxy, "http": proxy} if proxy else None
            resp = self._curl_session.get(url, headers=headers, timeout=15, proxies=proxies)

            if resp is not None and resp.status_code == 200:
                return resp

            if resp is None:
                logger.warning(
                    "G2 connection failed on attempt %d/%d",
                    attempt + 1, total_attempts,
                )

            elif resp.status_code == 429:
                logger.warning(
                    "G2 rate limited (429) on attempt %d/%d",
                    attempt + 1, total_attempts,
                )

            elif resp.status_code == 403:
                logger.warning(
                    "G2 blocked (403) on attempt %d/%d — "
                    "Cloudflare/Akamai bot detection",
                    attempt + 1, total_attempts,
                )
                # Try Playwright immediately on first 403 — no point
                # retrying curl_cffi when it's being TLS-fingerprinted.
                if attempt == 0:
                    pw_resp = self._browser_fetcher.fetch_playwright(url)
                    if pw_resp is not None:
                        logger.info(
                            "G2 Playwright fallback succeeded for %s", url,
                        )
                        return pw_resp

            else:
                logger.warning(
                    "G2 HTTP %d on attempt %d/%d",
                    resp.status_code, attempt + 1, total_attempts,
                )

            # --- Backoff / retry -------------------------------------------
            if self.rate_limiter.should_retry(attempt):
                self.rate_limiter.backoff(attempt + 1, source="G2")
                continue

            logger.error("G2 max retries exceeded for %s", url)
            return None

        return None

    def _get_product_url(self, product_name: str) -> Optional[str]:
        # Resolver-provided URL bypasses G2's own search entirely — that
        # search page is itself Cloudflare-gated, so when the resolver
        # has done the lookup via Brave we can jump straight to the
        # product page.
        if self.source_ref and self.source_ref.url:
            return self.source_ref.url
        slug = product_name.lower().replace(" ", "-")
        search_url = f"https://www.g2.com/search?query={product_name}"
        headers = {"User-Agent": _G2_USER_AGENT}
        resp = self._make_request(search_url, headers)
        if not resp:
            logger.warning(
                "G2 could not reach search page for '%s', guessing product URL",
                product_name,
            )
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

        headers = {"User-Agent": _G2_USER_AGENT}
        for page in range(1, self.config.max_pages + 1):
            url = f"{product_url}/reviews?page={page}"

            resp = self._make_request(url, headers)
            if not resp:
                logger.warning(
                    "G2 failed to fetch page %d for '%s', stopping pagination",
                    page, product_name,
                )
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            review_elements = soup.select("[class*='review']")

            if not review_elements:
                review_elements = soup.select("div[itemprop='review']")

            if not review_elements:
                logger.info(
                    "G2 no reviews found on page %d for '%s' (%s), stopping pagination",
                    page, product_name, url,
                )
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
                        rating = float(
                            rating_el.get("content", rating_el.get_text(strip=True))
                        )
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
