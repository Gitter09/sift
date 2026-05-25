import os
import yaml
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List, Optional

load_dotenv()


@dataclass
class RedditConfig:
    client_id: str = ""
    client_secret: str = ""
    subreddits: List[str] = field(default_factory=lambda: ["SaaS", "productivity", "startups", "software"])
    search_sort: str = "relevance"
    max_posts: int = 30
    max_comments_per_post: int = 15


@dataclass
class G2Config:
    request_delay: float = 2.0
    max_pages: int = 5
    user_agent_rotation: bool = True


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
class Settings:
    reddit: RedditConfig = field(default_factory=RedditConfig)
    g2: G2Config = field(default_factory=G2Config)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
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

    settings = Settings(
        reddit=RedditConfig(
            client_id=os.getenv("REDDIT_CLIENT_ID", reddit_raw.get("client_id", "")),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET", reddit_raw.get("client_secret", "")),
            subreddits=reddit_raw.get("subreddits", ["SaaS", "productivity", "startups", "software"]),
            search_sort=reddit_raw.get("search_sort", "relevance"),
            max_posts=reddit_raw.get("max_posts", 30),
            max_comments_per_post=reddit_raw.get("max_comments_per_post", 15),
        ),
        g2=G2Config(
            request_delay=float(os.getenv("G2_REQUEST_DELAY", g2_raw.get("request_delay", 2.0))),
            max_pages=g2_raw.get("max_pages", 5),
            user_agent_rotation=g2_raw.get("user_agent_rotation", True),
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
    )

    return settings
