import re
import time
import random
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from datetime import datetime
from src.models.feedback import FeedbackItem
from src.scrapers.base import BaseScraper
from src.config import G2Config

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


class G2Scraper(BaseScraper):
    def __init__(self, config: G2Config):
        self.config = config
        self.session = requests.Session()

    @property
    def source_name(self) -> str:
        return "g2"

    def _get_user_agent(self) -> str:
        if self.config.user_agent_rotation:
            return random.choice(USER_AGENTS)
        return USER_AGENTS[0]

    def _get_product_url(self, product_name: str) -> Optional[str]:
        slug = product_name.lower().replace(" ", "-")
        search_url = f"https://www.g2.com/search?query={product_name}"
        headers = {"User-Agent": self._get_user_agent()}
        try:
            resp = self.session.get(search_url, headers=headers, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[G2] Search request failed: {e}")
            return None

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
            print(f"[G2] Could not find product page for '{product_name}'")
            return items

        for page in range(1, self.config.max_pages + 1):
            url = f"{product_url}/reviews?page={page}"
            headers = {"User-Agent": self._get_user_agent()}

            try:
                time.sleep(self.config.request_delay)
                resp = self.session.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"[G2] Request failed for page {page}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            review_elements = soup.select("[class*='review']")

            if not review_elements:
                # Try alternative selectors
                review_elements = soup.select("div[itemprop='review']")

            if not review_elements:
                print(f"[G2] No reviews found on page {page}, stopping pagination")
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

                # Also try star rating from class names
                if rating is None:
                    star_el = review_el.select_one("[class*='stars']")
                    if star_el:
                        star_classes = star_el.get("class", [])
                        for cls in star_classes:
                            match = re.search(r"stars-(\d)", cls)
                            if match:
                                rating = float(match.group(1))

                author = None
                author_el = review_el.select_one("[itemprop='author']")
                if author_el:
                    author = author_el.get_text(strip=True)

                items.append(FeedbackItem(
                    source=self.source_name,
                    product=product_name,
                    text=text,
                    rating=rating,
                    url=url,
                    author=author,
                    metadata={"page": page},
                ))

            if len(items) >= 50:
                break

        print(f"[G2] Collected {len(items)} reviews for '{product_name}'")
        return items
