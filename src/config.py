import os
import logging
import sys
import yaml
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Dict, List

load_dotenv()


DEFAULT_ACTIVE_SOURCES = [
    "g2",
    "app_store",
    "play_store",
    "youtube",
    "hacker_news",
    "github_issues",
    "product_hunt",
    "stack_overflow",
    "dev_to",
    "support_forums",
    "changelogs",
    "discord_exports",
    "linkedin_comments",
]


@dataclass
class SourcesConfig:
    default_sources: List[str] = field(default_factory=lambda: DEFAULT_ACTIVE_SOURCES.copy())
    disabled_sources: List[str] = field(default_factory=lambda: ["reddit"])


@dataclass
class ProductProfileConfig:
    aliases: List[str] = field(default_factory=list)
    negative_terms: List[str] = field(default_factory=list)
    category: str = ""
    description: str = ""
    website: str = ""
    repos: List[str] = field(default_factory=list)
    slugs: List[str] = field(default_factory=list)
    app_ids: List[str] = field(default_factory=list)
    package_names: List[str] = field(default_factory=list)


@dataclass
class RelevanceConfig:
    enabled: bool = True
    threshold: float = 0.45
    min_items_before_relaxing: int = 3


@dataclass
class RedditConfig:
    client_id: str = ""
    client_secret: str = ""
    subreddits: List[str] = field(default_factory=lambda: ["SaaS", "productivity", "startups", "software"])
    search_sort: str = "relevance"
    max_posts: int = 30
    max_comments_per_post: int = 15
    # Rate limiting: Reddit API allows 100 QPM / 1000 per 10 min for OAuth.
    # We target 80 req/min to leave generous headroom for PRAW's internal calls.
    target_rate_per_minute: int = 80
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
    # Fall back to Playwright (real Chromium) when curl_cffi gets 403
    use_playwright_fallback: bool = True
    # Optional paid proxy URL (e.g. ScraperAPI, ZenRows) — required for reliable G2 access
    proxy_url: str = ""


@dataclass
class AppStoreConfig:
    app_ids: Dict[str, str] = field(default_factory=dict)
    countries: List[str] = field(default_factory=lambda: ["us"])
    max_pages: int = 1
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 30


@dataclass
class PlayStoreConfig:
    package_names: Dict[str, str] = field(default_factory=dict)
    countries: List[str] = field(default_factory=lambda: ["us"])
    languages: List[str] = field(default_factory=lambda: ["en"])
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


@dataclass
class YouTubeConfig:
    api_key: str = ""
    video_ids: Dict[str, List[str]] = field(default_factory=dict)
    max_videos: int = 5
    max_comments_per_video: int = 50
    order: str = "relevance"


@dataclass
class HackerNewsConfig:
    max_items: int = 50
    tags: str = "comment,story"
    request_delay: float = 1.0
    max_requests_per_minute: int = 30
    recency_days: int = 180


@dataclass
class GitHubIssuesConfig:
    token: str = ""
    repos: Dict[str, List[str]] = field(default_factory=dict)
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 30


@dataclass
class ProductHuntConfig:
    slugs: Dict[str, str] = field(default_factory=dict)
    max_items: int = 50
    request_delay: float = 2.0
    max_requests_per_minute: int = 20
    # Fall back to Playwright (real Chromium) when curl_cffi gets 403
    use_playwright_fallback: bool = True
    # Optional: get a free token at producthunt.com/v2/oauth/applications
    developer_token: str = ""


@dataclass
class SupportForumsConfig:
    search_urls: List[str] = field(default_factory=list)
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


@dataclass
class ChangelogsConfig:
    urls: Dict[str, List[str]] = field(default_factory=dict)
    search_urls: List[str] = field(default_factory=list)
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


@dataclass
class StackOverflowConfig:
    # Optional: register a free app at stackapps.com for 10k req/day (vs 300 without)
    api_key: str = ""
    sites: List[str] = field(default_factory=lambda: ["stackoverflow"])
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


@dataclass
class DevToConfig:
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


@dataclass
class DiscordExportsConfig:
    paths: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    max_items: int = 100
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


@dataclass
class LinkedInCommentsConfig:
    paths: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    max_items: int = 100
    request_delay: float = 1.0
    max_requests_per_minute: int = 20


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
    max_tokens: int = 8000


@dataclass
class LoggingConfig:
    level: str = "ERROR"
    format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


@dataclass
class Settings:
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    products: Dict[str, ProductProfileConfig] = field(default_factory=dict)
    relevance: RelevanceConfig = field(default_factory=RelevanceConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    g2: G2Config = field(default_factory=G2Config)
    app_store: AppStoreConfig = field(default_factory=AppStoreConfig)
    play_store: PlayStoreConfig = field(default_factory=PlayStoreConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    hacker_news: HackerNewsConfig = field(default_factory=HackerNewsConfig)
    github_issues: GitHubIssuesConfig = field(default_factory=GitHubIssuesConfig)
    product_hunt: ProductHuntConfig = field(default_factory=ProductHuntConfig)
    support_forums: SupportForumsConfig = field(default_factory=SupportForumsConfig)
    changelogs: ChangelogsConfig = field(default_factory=ChangelogsConfig)
    stack_overflow: StackOverflowConfig = field(default_factory=StackOverflowConfig)
    dev_to: DevToConfig = field(default_factory=DevToConfig)
    discord_exports: DiscordExportsConfig = field(default_factory=DiscordExportsConfig)
    linkedin_comments: LinkedInCommentsConfig = field(default_factory=LinkedInCommentsConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    max_feedback_per_source: int = 100


def load_settings(config_path: str = "config.yaml") -> Settings:
    yaml_data = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}

    sources_raw = yaml_data.get("sources", {})
    products_raw = yaml_data.get("products", {})
    relevance_raw = yaml_data.get("relevance", {})
    reddit_raw = yaml_data.get("reddit", {})
    g2_raw = yaml_data.get("g2", {})
    app_store_raw = yaml_data.get("app_store", {})
    play_store_raw = yaml_data.get("play_store", {})
    youtube_raw = yaml_data.get("youtube", {})
    hacker_news_raw = yaml_data.get("hacker_news", {})
    github_issues_raw = yaml_data.get("github_issues", {})
    product_hunt_raw = yaml_data.get("product_hunt", {})
    support_forums_raw = yaml_data.get("support_forums", {})
    changelogs_raw = yaml_data.get("changelogs", {})
    stack_overflow_raw = yaml_data.get("stack_overflow", {})
    dev_to_raw = yaml_data.get("dev_to", {})
    discord_exports_raw = yaml_data.get("discord_exports", {})
    linkedin_comments_raw = yaml_data.get("linkedin_comments", {})
    clustering_raw = yaml_data.get("clustering", {})
    llm_raw = yaml_data.get("llm", {})
    logging_raw = yaml_data.get("logging", {})

    # Handle tuple-type jitter_range from YAML (stored as list)
    g2_jitter = g2_raw.get("jitter_range", [0.5, 1.5])
    if isinstance(g2_jitter, list):
        g2_jitter = tuple(g2_jitter)

    settings = Settings(
        sources=SourcesConfig(
            default_sources=sources_raw.get("default_sources", DEFAULT_ACTIVE_SOURCES.copy()),
            disabled_sources=sources_raw.get("disabled_sources", ["reddit"]),
        ),
        products={
            name: ProductProfileConfig(
                aliases=profile.get("aliases", []) or [],
                negative_terms=profile.get("negative_terms", []) or [],
                category=profile.get("category", "") or "",
                description=profile.get("description", "") or "",
                website=profile.get("website", "") or "",
                repos=profile.get("repos", []) or [],
                slugs=profile.get("slugs", []) or [],
                app_ids=[
                    str(app_id)
                    for app_id in (profile.get("app_ids", []) or [])
                ],
                package_names=profile.get("package_names", []) or [],
            )
            for name, profile in products_raw.items()
            if isinstance(profile, dict)
        },
        relevance=RelevanceConfig(
            enabled=relevance_raw.get("enabled", True),
            threshold=float(relevance_raw.get("threshold", 0.45)),
            min_items_before_relaxing=relevance_raw.get("min_items_before_relaxing", 3),
        ),
        reddit=RedditConfig(
            client_id=os.getenv("REDDIT_CLIENT_ID", reddit_raw.get("client_id", "")),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET", reddit_raw.get("client_secret", "")),
            subreddits=reddit_raw.get("subreddits", ["SaaS", "productivity", "startups", "software"]),
            search_sort=reddit_raw.get("search_sort", "relevance"),
            max_posts=reddit_raw.get("max_posts", 30),
            max_comments_per_post=reddit_raw.get("max_comments_per_post", 15),
            target_rate_per_minute=reddit_raw.get("target_rate_per_minute", 80),
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
            use_playwright_fallback=g2_raw.get("use_playwright_fallback", True),
            proxy_url=os.getenv("G2_PROXY_URL", g2_raw.get("proxy_url", "")),
        ),
        app_store=AppStoreConfig(
            app_ids=app_store_raw.get("app_ids", {}),
            countries=app_store_raw.get("countries", ["us"]),
            max_pages=app_store_raw.get("max_pages", 1),
            max_items=app_store_raw.get("max_items", 50),
            request_delay=app_store_raw.get("request_delay", 1.0),
            max_requests_per_minute=app_store_raw.get("max_requests_per_minute", 30),
        ),
        play_store=PlayStoreConfig(
            package_names=play_store_raw.get("package_names", {}),
            countries=play_store_raw.get("countries", ["us"]),
            languages=play_store_raw.get("languages", ["en"]),
            max_items=play_store_raw.get("max_items", 50),
            request_delay=play_store_raw.get("request_delay", 1.0),
            max_requests_per_minute=play_store_raw.get("max_requests_per_minute", 20),
        ),
        youtube=YouTubeConfig(
            api_key=os.getenv("YOUTUBE_API_KEY", youtube_raw.get("api_key", "")),
            video_ids=youtube_raw.get("video_ids", {}),
            max_videos=youtube_raw.get("max_videos", 5),
            max_comments_per_video=youtube_raw.get("max_comments_per_video", 50),
            order=youtube_raw.get("order", "relevance"),
        ),
        hacker_news=HackerNewsConfig(
            max_items=hacker_news_raw.get("max_items", 50),
            tags=hacker_news_raw.get("tags", "comment,story"),
            request_delay=hacker_news_raw.get("request_delay", 1.0),
            max_requests_per_minute=hacker_news_raw.get("max_requests_per_minute", 30),
            recency_days=hacker_news_raw.get("recency_days", 180),
        ),
        github_issues=GitHubIssuesConfig(
            token=os.getenv("GITHUB_TOKEN", github_issues_raw.get("token", "")),
            repos=github_issues_raw.get("repos", {}),
            max_items=github_issues_raw.get("max_items", 50),
            request_delay=github_issues_raw.get("request_delay", 1.0),
            max_requests_per_minute=github_issues_raw.get("max_requests_per_minute", 30),
        ),
        product_hunt=ProductHuntConfig(
            slugs=product_hunt_raw.get("slugs", {}),
            max_items=product_hunt_raw.get("max_items", 50),
            request_delay=product_hunt_raw.get("request_delay", 2.0),
            max_requests_per_minute=product_hunt_raw.get("max_requests_per_minute", 20),
            use_playwright_fallback=product_hunt_raw.get("use_playwright_fallback", True),
            developer_token=os.getenv("PRODUCT_HUNT_TOKEN", product_hunt_raw.get("developer_token", "")),
        ),
        support_forums=SupportForumsConfig(
            search_urls=support_forums_raw.get("search_urls", []),
            max_items=support_forums_raw.get("max_items", 50),
            request_delay=support_forums_raw.get("request_delay", 1.0),
            max_requests_per_minute=support_forums_raw.get("max_requests_per_minute", 20),
        ),
        changelogs=ChangelogsConfig(
            urls=changelogs_raw.get("urls", {}),
            search_urls=changelogs_raw.get("search_urls", []),
            max_items=changelogs_raw.get("max_items", 50),
            request_delay=changelogs_raw.get("request_delay", 1.0),
            max_requests_per_minute=changelogs_raw.get("max_requests_per_minute", 20),
        ),
        stack_overflow=StackOverflowConfig(
            api_key=os.getenv("STACK_OVERFLOW_KEY", stack_overflow_raw.get("api_key", "")),
            sites=stack_overflow_raw.get("sites", ["stackoverflow"]),
            max_items=stack_overflow_raw.get("max_items", 50),
            request_delay=stack_overflow_raw.get("request_delay", 1.0),
            max_requests_per_minute=stack_overflow_raw.get("max_requests_per_minute", 20),
        ),
        dev_to=DevToConfig(
            max_items=dev_to_raw.get("max_items", 50),
            request_delay=dev_to_raw.get("request_delay", 1.0),
            max_requests_per_minute=dev_to_raw.get("max_requests_per_minute", 20),
        ),
        discord_exports=DiscordExportsConfig(
            paths=discord_exports_raw.get("paths", []),
            urls=discord_exports_raw.get("urls", []),
            max_items=discord_exports_raw.get("max_items", 100),
            request_delay=discord_exports_raw.get("request_delay", 1.0),
            max_requests_per_minute=discord_exports_raw.get("max_requests_per_minute", 20),
        ),
        linkedin_comments=LinkedInCommentsConfig(
            paths=linkedin_comments_raw.get("paths", []),
            urls=linkedin_comments_raw.get("urls", []),
            max_items=linkedin_comments_raw.get("max_items", 100),
            request_delay=linkedin_comments_raw.get("request_delay", 1.0),
            max_requests_per_minute=linkedin_comments_raw.get("max_requests_per_minute", 20),
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
            max_tokens=llm_raw.get("max_tokens", 8000),
        ),
        max_feedback_per_source=int(os.getenv("MAX_FEEDBACK_PER_SOURCE", "100")),
        logging=LoggingConfig(
            level=yaml_data.get("logging", {}).get("level", "ERROR"),
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
