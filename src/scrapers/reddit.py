import praw
from typing import List
from datetime import datetime
from src.models.feedback import FeedbackItem
from src.scrapers.base import BaseScraper
from src.config import RedditConfig


class RedditScraper(BaseScraper):
    def __init__(self, config: RedditConfig):
        self.config = config
        self.reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            user_agent="product-copilot/0.1 (research tool)",
        )

    @property
    def source_name(self) -> str:
        return "reddit"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        items: List[FeedbackItem] = []
        seen_texts = set()

        for subreddit_name in self.config.subreddits:
            subreddit = self.reddit.subreddit(subreddit_name)
            try:
                results = subreddit.search(
                    product_name,
                    sort=self.config.search_sort,
                    limit=self.config.max_posts,
                )
            except Exception as e:
                print(f"[Reddit] Error searching r/{subreddit_name}: {e}")
                continue

            for post in results:
                post_text = f"{post.title} {post.selftext}".strip()
                if post_text and post_text not in seen_texts:
                    seen_texts.add(post_text)
                    items.append(FeedbackItem(
                        source=self.source_name,
                        product=product_name,
                        text=post_text,
                        url=f"https://reddit.com{post.permalink}",
                        author=str(post.author),
                        date=datetime.fromtimestamp(post.created_utc),
                        metadata={"subreddit": subreddit_name, "score": post.score, "num_comments": post.num_comments},
                    ))

                if len(items) >= self.config.max_posts * len(self.config.subreddits):
                    break

                try:
                    post.comments.replace_more(limit=0)
                    for comment in post.comments[:self.config.max_comments_per_post]:
                        comment_text = comment.body.strip()
                        if comment_text and comment_text not in seen_texts and len(comment_text) > 20:
                            seen_texts.add(comment_text)
                            items.append(FeedbackItem(
                                source=self.source_name,
                                product=product_name,
                                text=comment_text,
                                url=f"https://reddit.com{comment.permalink}",
                                author=str(comment.author),
                                date=datetime.fromtimestamp(comment.created_utc),
                                metadata={"subreddit": subreddit_name, "score": comment.score},
                            ))
                except Exception:
                    pass

                if len(items) >= self.config.max_posts * len(self.config.subreddits):
                    break

        return items
