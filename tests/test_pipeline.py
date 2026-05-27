import numpy as np
from sift.models.feedback import FeedbackItem
from sift.models.cluster import ClusterResult
from sift.config import ClusteringConfig
from sift.pipeline.embedder import Embedder
from sift.pipeline.clusterer import Clusterer


# Use a lightweight config for tests
TEST_CLUSTERING_CONFIG = ClusteringConfig(
    embedding_model="all-MiniLM-L12-v2",
    umap_n_neighbors=2,
    umap_n_components=2,
    hdbscan_min_cluster_size=2,
    hdbscan_min_samples=1,
)


def _make_feedback(n: int, product: str = "TestProduct") -> list[FeedbackItem]:
    """Generate synthetic feedback items for testing."""
    complaints = [
        "The app is extremely slow and takes forever to load pages",
        "Loading times are terrible, I have to wait 30 seconds for each page",
        "The sync feature is broken and never works properly",
        "Sync constantly fails and I lose my work",
        "The pricing is way too high for what you get",
        "Way too expensive, the free tier is basically useless",
        "Customer support is non-existent, nobody responds to tickets",
        "I've been waiting 2 weeks for a support response",
        "The mobile app is basically unusable, crashes every time",
        "Mobile experience is garbage, nothing works on my phone",
    ]
    items = []
    for i in range(min(n, len(complaints))):
        items.append(FeedbackItem(
            source="test",
            product=product,
            text=complaints[i],
        ))
    return items


def test_embedder():
    items = _make_feedback(5)
    embedder = Embedder(TEST_CLUSTERING_CONFIG)
    embeddings = embedder.embed(items)
    assert embeddings.shape[0] == 5
    assert embeddings.shape[1] > 0
    # Check embeddings are normalized (cosine similarity ready)
    norms = np.linalg.norm(embeddings, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=0.01)


def test_clusterer_with_enough_items():
    items = _make_feedback(10)
    embedder = Embedder(TEST_CLUSTERING_CONFIG)
    embeddings = embedder.embed(items)

    clusterer = Clusterer(TEST_CLUSTERING_CONFIG)
    clusters = clusterer.cluster(embeddings, items)
    assert len(clusters) > 0
    total_items = sum(c.size for c in clusters)
    assert total_items <= 10  # some may be classified as noise


def test_clusterer_with_few_items():
    items = _make_feedback(2)
    clusterer = Clusterer(TEST_CLUSTERING_CONFIG)
    # Embeddings not needed for < 3 items (returns single group)
    fake_embeddings = np.zeros((2, 10))
    clusters = clusterer.cluster(fake_embeddings, items)
    assert len(clusters) == 1
    assert clusters[0].cluster_id == 0
    assert clusters[0].size == 2
