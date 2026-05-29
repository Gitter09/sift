"""Layer 2 (anchor similarity) tests."""

import numpy as np

from sift.config import DisambiguatorConfig
from sift.models import ProductContext
from sift.pipeline.anchor import AnchorSimilarityFilter, ProductAnchor
from sift.pipeline.resolver.models import ProductProfile


class _FakeEmbedder:
    def embed_profile(self, text):
        return np.array([1.0, 0.0])


def test_build_text_prefers_rich_profile():
    profile = ProductProfile(
        name="Notion",
        homepage="https://notion.so",
        description="The connected workspace for docs and notes",
        category="productivity",
        site_name="Notion",
        search_snippets=["Notion – one workspace", "Notion templates gallery", "third snippet ignored"],
        raw_metadata={"og:title": "Notion – Your connected workspace"},
    )
    context = ProductContext(canonical_name="Notion", description="ctx desc", category="ctx cat")

    text = ProductAnchor.build_text(profile, context)

    assert "connected workspace" in text
    assert "productivity" in text
    assert "og:title" not in text and "Your connected workspace" in text  # homepage title used
    # Only top-2 snippets are included.
    assert "one workspace" in text and "third snippet ignored" not in text
    # Falls back to profile, not the thinner ProductContext.
    assert "ctx desc" not in text


def test_build_text_falls_back_to_context():
    context = ProductContext(
        canonical_name="OpenCode",
        description="terminal coding agent",
        category="AI coding agent",
    )

    text = ProductAnchor.build_text(None, context)

    assert "terminal coding agent" in text
    assert "AI coding agent" in text


def test_vector_none_when_no_anchor_text():
    context = ProductContext(canonical_name="", description="", category="")
    anchor = ProductAnchor(_FakeEmbedder())

    assert anchor.vector(None, context) is None


def test_combined_none_anchor_returns_heuristic():
    f = AnchorSimilarityFilter(DisambiguatorConfig())
    anchor_score, combined = f.combined(np.array([1.0, 0.0]), None, heuristic_score=0.7, ambiguous=False)

    assert anchor_score is None
    assert combined == 0.7


def test_combined_cosine_normalized_and_weighted():
    cfg = DisambiguatorConfig(anchor_weight_normal=0.4)
    f = AnchorSimilarityFilter(cfg)
    anchor = np.array([1.0, 0.0])

    # Identical unit vectors -> cosine 1 -> anchor_score 1.0
    a_score, combined = f.combined(np.array([1.0, 0.0]), anchor, heuristic_score=0.5, ambiguous=False)
    assert a_score == 1.0
    assert combined == 0.5 * 0.6 + 1.0 * 0.4

    # Opposite vector -> cosine -1 -> anchor_score 0.0
    a_score, _ = f.combined(np.array([-1.0, 0.0]), anchor, heuristic_score=0.5, ambiguous=False)
    assert a_score == 0.0

    # Orthogonal -> cosine 0 -> anchor_score 0.5
    a_score, _ = f.combined(np.array([0.0, 1.0]), anchor, heuristic_score=0.5, ambiguous=False)
    assert a_score == 0.5


def test_combined_flips_weights_for_ambiguous():
    cfg = DisambiguatorConfig(anchor_weight_normal=0.4, anchor_weight_ambiguous=0.6)
    f = AnchorSimilarityFilter(cfg)
    anchor = np.array([1.0, 0.0])
    item = np.array([1.0, 0.0])  # anchor_score 1.0

    _, normal = f.combined(item, anchor, heuristic_score=0.2, ambiguous=False)
    _, ambiguous = f.combined(item, anchor, heuristic_score=0.2, ambiguous=True)

    # Ambiguous leans on the anchor (high here), so combined is higher.
    assert ambiguous > normal
    assert ambiguous == 0.2 * 0.4 + 1.0 * 0.6
