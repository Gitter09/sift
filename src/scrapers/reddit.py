import time
import logging
import praw
from typing import List
from datetime import datetime
from src.models.feedback import FeedbackItem
from src.scrapers.base import BaseScraper
from src.config import RedditConfig
from src.pipeline.rate_limiter import PrawRateMonitor

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    # Reddit API rate limits (OAuth script apps):
    #   - 60 requests per minute (10-minute rolling window, per OAuth client)
    #   - PRAW auto-handles X-Ratelimit-* headers and sleeps appropriately
    #   - We set ratelimit_seconds=300 so PRAW auto-waits up to 5min on rate limit errors
    #   - We target 50 req/min to leave headroom for PRAW's internal calls
    #   - X-Ratelimit-Used, X-Ratelimit-Remaining, X-Ratelimit-Reset headers in responses

    def __init__(self, config: RedditConfig):
        self.config = config
        self.reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            user_agent="sift/0.1 (product research tool)",
            ratelimit_seconds=config.praw_ratelimit_seconds,
        )
        self.rate_monitor = PrawRateMonitor(target_rate=config.target_rate_per_minute)

    @property
    def source_name(self) -> str:
        return "reddit"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        items: List[FeedbackItem] = []

        for subreddit_name in self.config.subreddits:
            # Delay between subreddit searches to pace our requests
            if items:  # skip delay on first subreddit
                time.sleep(self.config.subreddit_delay)

            subreddit = self.reddit.subreddit(subreddit_name)
            try:
                results = subreddit.search(
                    product_name,
                    sort=self.config.search_sort,
                    limit=self.config.max_posts,
                )
            except praw.exceptions.RedditAPIException as e:
                logger.warning(
                    "Reddit rate limit hit on r/%s. Waiting 60s before trying next subreddit. (%s)",
                    subreddit_name, e,
                )
                time.sleep(60)
                continue
            except Exception as e:
                logger.error(
                    "Failed to search r/%s for '%s': %s",
                    subreddit_name, product_name, e,
                )
                continue

            for post in results:
                self.rate_monitor.record_request()
                self.rate_monitor.ensure_pace()

                post_text = f"{post.title} {post.selftext}".strip()
                if post_text:
                    items.append(FeedbackItem(
                        source=self.source_name,
                        product=product_name,
                        text=post_text,
                        url=f"https://reddit.com{post.permalink}",
                        date=datetime.fromtimestamp(post.created_utc),
                        metadata={
                            "subreddit": subreddit_name,
                            "reddit_id": post.id,
                            "score": post.score,
                            "num_comments": post.num_comments,
                        },
                    ))

                if len(items) >= self.config.max_posts * len(self.config.subreddits):
                    break

                try:
                    post.comments.replace_more(limit=0)
                    for comment in post.comments[:self.config.max_comments_per_post]:
                        self.rate_monitor.record_request()
                        self.rate_monitor.ensure_pace()

                        comment_text = comment.body.strip()
                        if comment_text and len(comment_text) > 20:
                            items.append(FeedbackItem(
                                source=self.source_name,
                                product=product_name,
                                text=comment_text,
                                url=f"https://reddit.com{comment.permalink}",
                                date=datetime.fromtimestamp(comment.created_utc),
                                metadata={
                                    "subreddit": subreddit_name,
                                    "reddit_id": comment.id,
                                    "score": comment.score,
                                },
                            ))
                except praw.exceptions.RedditAPIException as e:
                    logger.warning(
                        "Reddit rate limit hit while fetching comments in r/%s. "
                        "Waiting 60s before continuing. (%s)",
                        subreddit_name, e,
                    )
                    time.sleep(60)
                except Exception as e:
                    logger.warning(
                        "Error fetching comments for post in r/%s: %s",
                        subreddit_name, e,
                    )

                if len(items) >= self.config.max_posts * len(self.config.subreddits):
                    break

        logger.info(
            "Reddit: collected %d items for '%s' (API requests: ~%d)",
            len(items), product_name, self.rate_monitor._request_count,
        )
        return items
