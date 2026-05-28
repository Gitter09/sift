from sift.pipeline.dedup import DedupFilter
from sift.models import FeedbackItem


def test_dedup_filter_unique_items():
    f = DedupFilter()
    items = [
        FeedbackItem(source="reddit", product="P", text="a", url="http://a.com/1"),
        FeedbackItem(source="reddit", product="P", text="b", url="http://a.com/2"),
        FeedbackItem(source="reddit", product="P", text="c", url="http://a.com/3"),
    ]
    result = f.filter(items)
    assert len(result) == 3
    assert f.seen_count == 3


def test_dedup_filter_duplicates():
    f = DedupFilter()
    item = FeedbackItem(source="reddit", product="P", text="dup", url="http://a.com/1")
    items = [item, item]
    result = f.filter(items)
    assert len(result) == 1
    assert f.seen_count == 1


def test_dedup_filter_cross_call():
    """Subsequent calls should also deduplicate against previously seen IDs."""
    f = DedupFilter()
    item1 = FeedbackItem(source="reddit", product="P", text="a", url="http://a.com/1")
    item2 = FeedbackItem(source="reddit", product="P", text="b", url="http://a.com/2")

    result1 = f.filter([item1, item2])
    assert len(result1) == 2

    result2 = f.filter([item1, item2])
    assert len(result2) == 0  # both already seen
    assert f.seen_count == 2


def test_dedup_filter_reset():
    f = DedupFilter()
    item = FeedbackItem(source="reddit", product="P", text="a", url="http://a.com/1")
    f.filter([item])
    assert f.seen_count == 1
    f.reset()
    assert f.seen_count == 0
    result = f.filter([item])
    assert len(result) == 1


def test_dedup_filter_different_sources_same_url():
    """Items from different sources with the same URL should NOT collide."""
    f = DedupFilter()
    item1 = FeedbackItem(source="reddit", product="P", text="a", url="http://example.com/1")
    item2 = FeedbackItem(source="g2", product="P", text="b", url="http://example.com/1")
    result = f.filter([item1, item2])
    assert len(result) == 2
    assert item1.id != item2.id
