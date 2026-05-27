import os
import logging
import tempfile
from unittest.mock import patch
from sift.config import (
    load_settings, setup_logging, Settings,
    RedditConfig, G2Config, ClusteringConfig, LLMConfig, LoggingConfig,
)


def test_load_settings_defaults():
    with patch.dict(os.environ, {"LLM_BASE_URL": "", "LLM_MODEL": ""}, clear=False):
        os.environ.pop("LLM_BASE_URL", None)
        os.environ.pop("LLM_MODEL", None)
        settings = load_settings()
    assert isinstance(settings, Settings)
    assert settings.clustering.embedding_model == "all-MiniLM-L12-v2"
    assert settings.g2.request_delay == 2.5
    assert settings.g2.max_requests_per_minute == 12
    assert settings.reddit.target_rate_per_minute == 80
    assert settings.reddit.praw_ratelimit_seconds == 300
    assert settings.llm.base_url == "https://api.openai.com/v1"
    assert settings.logging.level == "ERROR"
    assert settings.relevance.enabled is True
    assert settings.relevance.threshold == 0.45
    assert "reddit" in settings.sources.disabled_sources
    assert "g2" in settings.sources.default_sources
    assert "hacker_news" in settings.sources.default_sources


def test_logging_config_from_yaml():
    yaml_content = """
logging:
  level: "DEBUG"
  format: "custom format"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        settings = load_settings(f.name)
        assert settings.logging.level == "DEBUG"
        assert settings.logging.format == "custom format"
        os.unlink(f.name)


def test_load_settings_from_yaml():
    yaml_content = """
sources:
  default_sources:
    - g2
    - hacker_news
  disabled_sources:
    - reddit
reddit:
  max_posts: 10
  target_rate_per_minute: 40
g2:
  request_delay: 3.0
  max_requests_per_minute: 8
relevance:
  enabled: false
  threshold: 0.6
products:
  Droid:
    aliases:
      - Factory Droid
    negative_terms:
      - Android
    category: AI coding agent
    description: Factory coding agent
    website: factory.ai
    repos:
      - factory/droid
clustering:
  embedding_model: "all-MiniLM-L12-v2"
  hdbscan_min_cluster_size: 5
llm:
  model: "gpt-4o"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        with patch.dict(os.environ, {"LLM_MODEL": ""}, clear=False):
            os.environ.pop("LLM_MODEL", None)
            settings = load_settings(f.name)
        assert settings.reddit.max_posts == 10
        assert settings.reddit.target_rate_per_minute == 40
        assert settings.sources.default_sources == ["g2", "hacker_news"]
        assert settings.sources.disabled_sources == ["reddit"]
        assert settings.g2.request_delay == 3.0
        assert settings.g2.max_requests_per_minute == 8
        assert settings.relevance.enabled is False
        assert settings.relevance.threshold == 0.6
        assert settings.products["Droid"].aliases == ["Factory Droid"]
        assert settings.products["Droid"].negative_terms == ["Android"]
        assert settings.products["Droid"].repos == ["factory/droid"]
        assert settings.clustering.hdbscan_min_cluster_size == 5
        assert settings.llm.model == "gpt-4o"
        os.unlink(f.name)


def test_env_override():
    os.environ["LLM_API_KEY"] = "test-key-123"
    os.environ["LLM_BASE_URL"] = "http://localhost:8080/v1"
    settings = load_settings()
    assert settings.llm.api_key == "test-key-123"
    assert settings.llm.base_url == "http://localhost:8080/v1"
    # Clean up
    os.environ.pop("LLM_API_KEY", None)
    os.environ.pop("LLM_BASE_URL", None)


def test_setup_logging():
    settings = load_settings()
    setup_logging(settings, verbose=False)
    sift_logger = logging.getLogger("sift")
    assert sift_logger.level == logging.ERROR

    setup_logging(settings, verbose=True)
    assert sift_logger.level == logging.DEBUG
