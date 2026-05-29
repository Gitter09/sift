"""Integration tests for the three-layer ContentDisambiguator.

A fake embedder injects deterministic vectors so triage outcomes are
controllable without loading the real sentence-transformer model or hitting an
LLM (the gate is disabled, so the uncertain band falls back to combined score).
"""

import numpy as np

from sift.config import ClusteringConfig, DisambiguatorConfig, LLMConfig
from sift.models import FeedbackItem, ProductContext
from sift.pipeline.anchor import ProductAnchor
from sift.pipeline.disambiguator import ContentDisambiguator

# Unit vectors in 2-D. Anchor is [1, 0]:
#   _MATCH  -> cosine  1 -> anchor_score 1.0
#   _OFF    -> cosine -1 -> anchor_score 0.0
#   _MID    -> cosine  0 -> anchor_score 0.5
_ANCHOR = np.array([1.0, 0.0])
_VECS = {"match": np.array([1.0, 0.0]), "off": np.array([-1.0, 0.0]), "mid": np.array([0.0, 1.0])}


class _FakeEmbedder:
    def embed(self, items):
        return np.array([_VECS[it.text] for it in items], dtype=float)

    def embed_profile(self, text):
        return _ANCHOR


def _disambiguator(**cfg_overrides) -> ContentDisambiguator:
    # Gate disabled -> uncertain band decided by combined vs midpoint (deterministic).
    cfg = DisambiguatorConfig(llm_gate_enabled=False, **cfg_overrides)
    d = ContentDisambiguator(cfg, LLMConfig(api_key=""), ClusteringConfig())
    fake = _FakeEmbedder()
    d._embedder = fake
    d._anchor = ProductAnchor(fake)
    return d


def _item(text: str, heuristic: float) -> FeedbackItem:
    it = FeedbackItem(source="reddit", product="OpenCode", text=text)
    it.metadata["relevance_score"] = heuristic
    return it


_CTX = ProductContext(canonical_name="OpenCode", description="terminal coding agent", category="AI coding agent")


def test_triage_routes_and_aligns_embeddings():
    d = _disambiguator()
    items = [
        _item("match", 0.8),  # combined 0.88 -> auto-keep
        _item("off", 0.2),    # combined 0.12 -> auto-reject
        _item("mid", 0.5),    # combined 0.50 -> uncertain -> 0.50 >= 0.45 -> keep
    ]
    result = d.resolve(items, _CTX, profile=None)

    kept_texts = {it.text for it in result.kept_items}
    assert kept_texts == {"match", "mid"}
    assert result.stats.auto_kept == 1
    assert result.stats.auto_rejected == 1
    assert result.stats.over_cap == 1  # uncertain decided by score (gate disabled)
    assert result.stats.final_kept == 2
    # Embeddings come back sliced 1:1 with kept items.
    assert result.kept_embeddings.shape == (2, 2)


def test_empty_input_returns_empty():
    d = _disambiguator()
    result = d.resolve([], _CTX, profile=None)
    assert result.kept_items == []
    assert result.stats.final_kept == 0


def test_safety_net_keeps_top_k_when_all_rejected():
    d = _disambiguator(safety_net_min_items=1)
    items = [
        _item("off", 0.05),  # combined 0.03
        _item("off", 0.10),  # combined 0.06
        _item("off", 0.20),  # combined 0.12  <- highest
    ]
    # Distinct ids despite same text/source require distinct urls.
    for i, it in enumerate(items):
        it.url = f"https://example.com/{i}"
        it.__post_init__()
        it.metadata["relevance_score"] = [0.05, 0.10, 0.20][i]

    result = d.resolve(items, _CTX, profile=None)

    assert result.stats.safety_net_triggered is True
    assert result.stats.final_kept == 1
    assert result.kept_items[0].metadata["relevance_score"] == 0.20
    assert result.kept_items[0].metadata["disambiguation"] == "keep:safety-net"


def test_ambiguous_anchor_floor_rejects_high_heuristic():
    d = _disambiguator()
    ctx = ProductContext(canonical_name="Notion", description="notes workspace", category="productivity")
    clear = _item("match", 0.9)        # ambiguous: combined 0.9*0.4 + 1.0*0.6 = 0.96 -> keep
    floored = _item("off", 0.95)       # anchor_score 0.0 < 0.35 -> reject despite high heuristic
    clear.url, floored.url = "https://x/1", "https://x/2"
    clear.__post_init__(); floored.__post_init__()
    clear.metadata["relevance_score"] = 0.9
    floored.metadata["relevance_score"] = 0.95

    result = d.resolve([clear, floored], ctx, profile=None)

    kept_texts = {it.text for it in result.kept_items}
    assert kept_texts == {"match"}
    assert floored.metadata["disambiguation"] == "reject:anchor-floor"


def test_prefilter_drops_garbage_before_resolve():
    d = _disambiguator()
    ctx = ProductContext(
        canonical_name="OpenCode",
        aliases=("opencode",),
        description="terminal coding agent",
        category="AI coding agent",
    )
    good = FeedbackItem(source="github_issues", product="OpenCode", text="opencode crashes on large repos")
    junk = FeedbackItem(source="reddit", product="OpenCode", text="completely unrelated weather chatter")

    kept, stats = d.prefilter([good, junk], ctx)

    assert good in kept and junk not in kept
    assert stats.dropped == 1
