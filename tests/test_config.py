import os
import tempfile
from src.config import load_settings, Settings, RedditConfig, G2Config, ClusteringConfig, LLMConfig


def test_load_settings_defaults():
    settings = load_settings()
    assert isinstance(settings, Settings)
    assert settings.clustering.embedding_model == "all-MiniLM-L12-v2"
    assert settings.g2.request_delay == 2.0
    assert settings.llm.base_url == "https://api.openai.com/v1"


def test_load_settings_from_yaml():
    yaml_content = """
reddit:
  max_posts: 10
g2:
  request_delay: 3.0
clustering:
  embedding_model: "all-MiniLM-L12-v2"
  hdbscan_min_cluster_size: 5
llm:
  model: "gpt-4o"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        settings = load_settings(f.name)
        assert settings.reddit.max_posts == 10
        assert settings.g2.request_delay == 3.0
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
