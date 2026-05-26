import os
import logging
import sys
import yaml
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List

load_dotenv()


@dataclass
class RedditConfig:
    client_id: str = ""
    client_secret: str = ""
    subreddits: List[str] = field(default_factory=lambda: ["SaaS", "productivity", "startups", "software"])
    search_sort: str = "relevance"
    max_posts: int = 30
    max_comments_per_post: int = 15
    # Rate limiting: Reddit API allows 100 QPM / 1000 per 10 min for OAuth.
    # We target 50 req/min to leave generous headroom for PRAW's internal calls.
    target_rate_per_minute: int = 50
    # PRAW's ratelimit_seconds: how long PRAW will auto-wait on Reddit rate limit errors.
    # Default in PRAW is 5s; we raise to 300s for resilience on long scraping runs.
    praw_ratelimit_seconds: int = 300
    # Delay between switching subreddits (seconds)
    subreddit_delay: float = 2.0


@dataclass
class G2Config:
    request_delay: float = 2.5  # increased from 2.0 — safer against Cloudflare
    max_pages: int = 5
    user_agent_rotation: bool = True
    # Rate limiting: G2 uses Cloudflare + Akamai. No published limits.
    # Practical safe threshold: ~10-15 req/min with delays + UA rotation.
    max_requests_per_minute: int = 12
    # Exponential backoff settings for 429/403 responses
    backoff_base: float = 2.0
    max_backoff: float = 60.0
    max_retries: int = 3
    # Jitter multiplier range applied to request_delay
    jitter_range: tuple = (0.5, 1.5)


@dataclass
class ClusteringConfig:
    embedding_model: str = "all-MiniLM-L12-v2"
    umap_n_neighbors: int = 15
    umap_n_components: int = 5
    hdbscan_min_cluster_size: int = 3
    hdbscan_min_samples: int = 1


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2000


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


@dataclass
class Settings:
    reddit: RedditConfig = field(default_factory=RedditConfig)
    g2: G2Config = field(default_factory=G2Config)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    max_feedback_per_source: int = 100


def load_settings(config_path: str = "config.yaml") -> Settings:
    yaml_data = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}

    reddit_raw = yaml_data.get("reddit", {})
    g2_raw = yaml_data.get("g2", {})
    clustering_raw = yaml_data.get("clustering", {})
    llm_raw = yaml_data.get("llm", {})
    logging_raw = yaml_data.get("logging", {})

    # Handle tuple-type jitter_range from YAML (stored as list)
    g2_jitter = g2_raw.get("jitter_range", [0.5, 1.5])
    if isinstance(g2_jitter, list):
        g2_jitter = tuple(g2_jitter)

    settings = Settings(
        reddit=RedditConfig(
            client_id=os.getenv("REDDIT_CLIENT_ID", reddit_raw.get("client_id", "")),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET", reddit_raw.get("client_secret", "")),
            subreddits=reddit_raw.get("subreddits", ["SaaS", "productivity", "startups", "software"]),
            search_sort=reddit_raw.get("search_sort", "relevance"),
            max_posts=reddit_raw.get("max_posts", 30),
            max_comments_per_post=reddit_raw.get("max_comments_per_post", 15),
            target_rate_per_minute=reddit_raw.get("target_rate_per_minute", 50),
            praw_ratelimit_seconds=reddit_raw.get("praw_ratelimit_seconds", 300),
            subreddit_delay=reddit_raw.get("subreddit_delay", 2.0),
        ),
        g2=G2Config(
            request_delay=float(os.getenv("G2_REQUEST_DELAY", g2_raw.get("request_delay", 2.5))),
            max_pages=g2_raw.get("max_pages", 5),
            user_agent_rotation=g2_raw.get("user_agent_rotation", True),
            max_requests_per_minute=g2_raw.get("max_requests_per_minute", 12),
            backoff_base=g2_raw.get("backoff_base", 2.0),
            max_backoff=g2_raw.get("max_backoff", 60.0),
            max_retries=g2_raw.get("max_retries", 3),
            jitter_range=g2_jitter,
        ),
        clustering=ClusteringConfig(
            embedding_model=clustering_raw.get("embedding_model", "all-MiniLM-L12-v2"),
            umap_n_neighbors=clustering_raw.get("umap_n_neighbors", 15),
            umap_n_components=clustering_raw.get("umap_n_components", 5),
            hdbscan_min_cluster_size=clustering_raw.get("hdbscan_min_cluster_size", 3),
            hdbscan_min_samples=clustering_raw.get("hdbscan_min_samples", 1),
        ),
        llm=LLMConfig(
            api_key=os.getenv("LLM_API_KEY", llm_raw.get("api_key", "")),
            base_url=os.getenv("LLM_BASE_URL", llm_raw.get("base_url", "https://api.openai.com/v1")),
            model=os.getenv("LLM_MODEL", llm_raw.get("model", "gpt-4o-mini")),
            temperature=llm_raw.get("temperature", 0.3),
            max_tokens=llm_raw.get("max_tokens", 2000),
        ),
        max_feedback_per_source=int(os.getenv("MAX_FEEDBACK_PER_SOURCE", "100")),
        logging=LoggingConfig(
            level=yaml_data.get("logging", {}).get("level", "INFO"),
            format=yaml_data.get("logging", {}).get(
                "format", "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
            ),
        ),
    )

    return settings


def setup_logging(settings: Settings, verbose: bool = False) -> None:
    """Configure the root logger for Sift based on settings.

    Called once at CLI startup. Subsequent modules use
    ``logging.getLogger(__name__)`` to get a properly configured logger.
    """
    level = logging.DEBUG if verbose else getattr(logging, settings.logging.level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(settings.logging.format))

    root_logger = logging.getLogger("src")
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False
