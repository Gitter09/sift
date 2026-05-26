import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Iterable, List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from src.config import (
    AppStoreConfig,
    ChangelogsConfig,
    DiscordExportsConfig,
    GitHubIssuesConfig,
    HackerNewsConfig,
    LinkedInCommentsConfig,
    PlayStoreConfig,
    ProductHuntConfig,
    SupportForumsConfig,
    YouTubeConfig,
)
from src.models.feedback import FeedbackItem
from src.pipeline.http_client import (
    CurlCffiSession,
    BrowserFetcher,
    HttpResponse,
)
from src.pipeline.rate_limiter import RateLimiter
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RequestsScraper(BaseScraper):
    def __init__(self, max_requests_per_minute: int = 20, request_delay: float = 1.0, use_playwright: bool = True):
        self._curl_session = CurlCffiSession()
        jitter = max(0.1, request_delay)
        self.rate_limiter = RateLimiter(
            max_requests_per_minute=max_requests_per_minute,
            jitter_range=(max(0.1, jitter * 0.75), jitter * 1.25),
            max_retries=2,
        )
        self._browser_fetcher = BrowserFetcher(self.rate_limiter, use_playwright=use_playwright)

    def _get_json(self, url: str, **kwargs) -> Optional[Any]:
        self.rate_limiter.wait()
        try:
            resp = self._curl_session.get(url, timeout=20, **kwargs)
            if resp is None:
                logger.warning("%s connection failed for %s", self.source_name, url)
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("%s failed to fetch JSON from %s: %s", self.source_name, url, e)
            return None

    def _get_html(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        self.rate_limiter.wait()

        # Tier 1: curl_cffi
        try:
            resp = self._curl_session.get(url, timeout=20, **kwargs)
            if resp is not None:
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.debug("%s curl_cffi fetch failed for %s: %s", self.source_name, url, e)

        # Tier 2: Playwright fallback
        pw_resp = self._browser_fetcher.fetch_playwright(url)
        if pw_resp is not None:
            return BeautifulSoup(pw_resp.text, "html.parser")

        logger.warning("%s failed to fetch HTML from %s", self.source_name, url)
        return None


class AppStoreScraper(RequestsScraper):
    def __init__(self, config: AppStoreConfig):
        super().__init__(config.max_requests_per_minute, config.request_delay)
        self.config = config

    @property
    def source_name(self) -> str:
        return "app_store"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        app_id = self.config.app_ids.get(product_name)
        if not app_id:
            logger.info("App Store app ID not configured for '%s', skipping.", product_name)
            return []

        items: List[FeedbackItem] = []
        for country in self.config.countries:
            for page in range(1, self.config.max_pages + 1):
                url = (
                    f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/"
                    f"id={app_id}/sortby=mostrecent/json"
                )
                data = self._get_json(url)
                entries = data.get("feed", {}).get("entry", []) if isinstance(data, dict) else []
                for entry in entries:
                    if "im:name" in entry:
                        continue
                    content = entry.get("content", {}).get("label", "")
                    title = entry.get("title", {}).get("label", "")
                    text = f"{title}\n\n{content}".strip()
                    if len(text) < 20:
                        continue
                    rating = _safe_float(entry.get("im:rating", {}).get("label"))
                    review_url = entry.get("link", {}).get("attributes", {}).get("href", url)
                    items.append(FeedbackItem(
                        source=self.source_name,
                        product=product_name,
                        text=text,
                        rating=rating,
                        url=review_url,
                        metadata={"country": country, "page": page},
                    ))
                    if len(items) >= self.config.max_items:
                        return items
        return items


class PlayStoreScraper(RequestsScraper):
    def __init__(self, config: PlayStoreConfig):
        super().__init__(config.max_requests_per_minute, config.request_delay)
        self.config = config

    @property
    def source_name(self) -> str:
        return "play_store"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        package_name = self.config.package_names.get(product_name)
        if not package_name:
            logger.info("Play Store package name not configured for '%s', skipping.", product_name)
            return []

        items: List[FeedbackItem] = []
        for country in self.config.countries:
            for language in self.config.languages:
                url = (
                    "https://play.google.com/store/apps/details"
                    f"?id={quote_plus(package_name)}&hl={language}&gl={country}&showAllReviews=true"
                )
                soup = self._get_html(url, headers={"User-Agent": "Mozilla/5.0"})
                if not soup:
                    continue
                for review in soup.select("[data-review-id]"):
                    text = review.get_text(" ", strip=True)
                    if len(text) < 20:
                        continue
                    items.append(FeedbackItem(
                        source=self.source_name,
                        product=product_name,
                        text=text,
                        url=url,
                        metadata={"country": country, "language": language},
                    ))
                    if len(items) >= self.config.max_items:
                        return items
        return items


class YouTubeScraper(RequestsScraper):
    def __init__(self, config: YouTubeConfig):
        super().__init__(max_requests_per_minute=60, request_delay=0.5)
        self.config = config

    @property
    def source_name(self) -> str:
        return "youtube"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        if not self.config.api_key:
            logger.info("YOUTUBE_API_KEY not set, skipping YouTube comments.")
            return []

        video_ids = self.config.video_ids.get(product_name, [])[: self.config.max_videos]
        if not video_ids:
            logger.info("YouTube video IDs not configured for '%s', skipping.", product_name)
            return []

        items: List[FeedbackItem] = []
        for video_id in video_ids:
            url = "https://www.googleapis.com/youtube/v3/commentThreads"
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(100, self.config.max_comments_per_video),
                "order": self.config.order,
                "textFormat": "plainText",
                "key": self.config.api_key,
            }
            data = self._get_json(url, params=params)
            for item in data.get("items", []) if isinstance(data, dict) else []:
                snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = snippet.get("textDisplay", "")
                if len(text) < 20:
                    continue
                comment_id = item.get("snippet", {}).get("topLevelComment", {}).get("id", "")
                items.append(FeedbackItem(
                    source=self.source_name,
                    product=product_name,
                    text=text,
                    url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                    date=_parse_datetime(snippet.get("publishedAt")),
                    metadata={"video_id": video_id, "like_count": snippet.get("likeCount")},
                ))
                if len(items) >= self.config.max_comments_per_video * max(1, len(video_ids)):
                    return items
        return items


class HackerNewsScraper(RequestsScraper):
    def __init__(self, config: HackerNewsConfig):
        super().__init__(config.max_requests_per_minute, config.request_delay)
        self.config = config

    @property
    def source_name(self) -> str:
        return "hacker_news"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        url = (
            "https://hn.algolia.com/api/v1/search"
            f"?query={quote_plus(product_name)}&tags={quote_plus(self.config.tags)}"
            f"&hitsPerPage={self.config.max_items}"
        )
        data = self._get_json(url)
        items: List[FeedbackItem] = []
        for hit in data.get("hits", []) if isinstance(data, dict) else []:
            text = _html_to_text(hit.get("comment_text") or hit.get("title") or hit.get("story_title") or "")
            if len(text) < 20:
                continue
            object_id = hit.get("objectID")
            items.append(FeedbackItem(
                source=self.source_name,
                product=product_name,
                text=text,
                url=f"https://news.ycombinator.com/item?id={object_id}" if object_id else None,
                date=_parse_datetime(hit.get("created_at")),
                metadata={"points": hit.get("points"), "story_title": hit.get("story_title")},
            ))
        return items[: self.config.max_items]


class GitHubIssuesScraper(RequestsScraper):
    def __init__(self, config: GitHubIssuesConfig):
        super().__init__(config.max_requests_per_minute, config.request_delay)
        self.config = config

    @property
    def source_name(self) -> str:
        return "github_issues"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        repos = self.config.repos.get(product_name, [])
        if not repos:
            logger.info("GitHub repos not configured for '%s', skipping.", product_name)
            return []

        headers = {"Accept": "application/vnd.github+json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        items: List[FeedbackItem] = []
        for repo in repos:
            query = quote_plus(f"repo:{repo} {product_name} is:issue")
            url = f"https://api.github.com/search/issues?q={query}&sort=updated&order=desc&per_page=50"
            data = self._get_json(url, headers=headers)
            for issue in data.get("items", []) if isinstance(data, dict) else []:
                text = f"{issue.get('title', '')}\n\n{issue.get('body') or ''}".strip()
                if len(text) < 20:
                    continue
                items.append(FeedbackItem(
                    source=self.source_name,
                    product=product_name,
                    text=text,
                    url=issue.get("html_url"),
                    date=_parse_datetime(issue.get("created_at")),
                    metadata={"repo": repo, "state": issue.get("state"), "comments": issue.get("comments")},
                ))
                if len(items) >= self.config.max_items:
                    return items
        return items


class ProductHuntScraper(RequestsScraper):
    def __init__(self, config: ProductHuntConfig):
        super().__init__(
            config.max_requests_per_minute,
            config.request_delay,
            use_playwright=config.use_playwright_fallback,
        )
        self.config = config

    @property
    def source_name(self) -> str:
        return "product_hunt"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        slug = self.config.slugs.get(product_name, product_name.lower().replace(" ", "-"))
        url = f"https://www.producthunt.com/products/{slug}"
        soup = self._get_html(url, headers={"User-Agent": "Mozilla/5.0"})
        if not soup:
            return []

        items: List[FeedbackItem] = []
        for element in soup.select("[data-test*='comment'], article, div[class*='comment']"):
            text = element.get_text(" ", strip=True)
            if len(text) < 30 or product_name.lower() not in text.lower():
                continue
            items.append(FeedbackItem(
                source=self.source_name,
                product=product_name,
                text=text,
                url=url,
                metadata={"slug": slug},
            ))
            if len(items) >= self.config.max_items:
                break
        return items


class SearchPageScraper(RequestsScraper):
    config: Any

    def _search_urls(self, product_name: str) -> Iterable[str]:
        for template in self.config.search_urls:
            yield template.format(query=quote_plus(product_name), product=quote_plus(product_name))

    def _items_from_pages(self, product_name: str) -> List[FeedbackItem]:
        items: List[FeedbackItem] = []
        for url in self._search_urls(product_name):
            soup = self._get_html(url, headers={"User-Agent": "Mozilla/5.0"})
            if not soup:
                continue
            for element in soup.select("article, main p, .post, .topic, .comment, li"):
                text = element.get_text(" ", strip=True)
                if len(text) < 40 or product_name.lower() not in text.lower():
                    continue
                items.append(FeedbackItem(
                    source=self.source_name,
                    product=product_name,
                    text=text,
                    url=url,
                ))
                if len(items) >= self.config.max_items:
                    return items
        return items


class SupportForumsScraper(SearchPageScraper):
    def __init__(self, config: SupportForumsConfig):
        super().__init__(config.max_requests_per_minute, config.request_delay)
        self.config = config

    @property
    def source_name(self) -> str:
        return "support_forums"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        if not self.config.search_urls:
            logger.info("Support forum search URLs not configured, skipping.")
            return []
        return self._items_from_pages(product_name)


class ChangelogScraper(SearchPageScraper):
    def __init__(self, config: ChangelogsConfig):
        super().__init__(config.max_requests_per_minute, config.request_delay)
        self.config = config

    @property
    def source_name(self) -> str:
        return "changelogs"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        urls = self.config.urls.get(product_name, [])
        items: List[FeedbackItem] = []
        for url in urls:
            soup = self._get_html(url, headers={"User-Agent": "Mozilla/5.0"})
            if not soup:
                continue
            for element in soup.select("article, main, section, li, p"):
                text = element.get_text(" ", strip=True)
                if len(text) < 40:
                    continue
                items.append(FeedbackItem(
                    source=self.source_name,
                    product=product_name,
                    text=text,
                    url=url,
                ))
                if len(items) >= self.config.max_items:
                    return items

        if self.config.search_urls and len(items) < self.config.max_items:
            items.extend(self._items_from_pages(product_name))
        return items[: self.config.max_items]


class JsonExportScraper(BaseScraper):
    def __init__(self, paths: List[str], urls: List[str], max_items: int):
        self.paths = paths
        self.urls = urls
        self.max_items = max_items

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        items: List[FeedbackItem] = []
        for path in self.paths:
            if not os.path.exists(path):
                logger.warning("%s export path does not exist: %s", self.source_name, path)
                continue
            with open(path, "r") as f:
                raw = json.load(f)
            items.extend(self._parse_records(raw, product_name, path))
            if len(items) >= self.max_items:
                return items[: self.max_items]

        for url in self.urls:
            try:
                resp = curl_requests.get(url, timeout=20)
                resp.raise_for_status()
                items.extend(self._parse_records(resp.json(), product_name, url))
            except (curl_requests.RequestException, ValueError) as e:
                logger.warning("%s failed to fetch export %s: %s", self.source_name, url, e)
        return items[: self.max_items]

    def _parse_records(self, raw: Any, product_name: str, origin: str) -> List[FeedbackItem]:
        records = raw if isinstance(raw, list) else raw.get("messages", raw.get("comments", [])) if isinstance(raw, dict) else []
        items: List[FeedbackItem] = []
        for record in records:
            text = self._record_text(record)
            if len(text) < 20 or product_name.lower() not in text.lower():
                continue
            items.append(FeedbackItem(
                source=self.source_name,
                product=product_name,
                text=text,
                url=record.get("url") if isinstance(record, dict) else origin,
                date=_parse_datetime(record.get("timestamp") or record.get("created_at")) if isinstance(record, dict) else None,
                metadata={"origin": origin},
            ))
        return items

    def _record_text(self, record: Any) -> str:
        if isinstance(record, str):
            return record
        if not isinstance(record, dict):
            return ""
        value = record.get("content") or record.get("text") or record.get("body") or record.get("comment") or ""
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        return str(value)


class DiscordExportsScraper(JsonExportScraper):
    def __init__(self, config: DiscordExportsConfig):
        super().__init__(config.paths, config.urls, config.max_items)

    @property
    def source_name(self) -> str:
        return "discord_exports"


class LinkedInCommentsScraper(JsonExportScraper):
    def __init__(self, config: LinkedInCommentsConfig):
        super().__init__(config.paths, config.urls, config.max_items)

    @property
    def source_name(self) -> str:
        return "linkedin_comments"


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _html_to_text(value: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(value, "html.parser").get_text(" ", strip=True)).strip()
