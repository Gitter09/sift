"""Persisted EMA wall-clock timings used to drive the estimated-progress bar.

The :class:`EstimatedTask` in :mod:`sift.ui._estimator` needs an *expected
duration* for every scraper and pipeline stage so the bar can fill smoothly
between real events. We can't know those durations a priori, so:

  1. Ship hand-curated ``SEED_TIMINGS`` for first-run users (no history yet).
  2. After every observed run, fold the real duration into a per-key
     exponential moving average and persist it to
     ``~/.config/sift/timings.json``.
  3. On the next run, ``get()`` returns the EMA — improving smoothness
     run-over-run without ever re-touching code.

Concurrency:
  - ``record()`` mutates the in-process cache under a lock. ``flush()`` writes
    the whole dict atomically (write to ``<path>.tmp`` then ``os.replace``).
  - The estimator only calls ``get()`` (read-only), so the hot path is
    lock-free after the initial load.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Dict

logger = logging.getLogger(__name__)

# EMA smoothing factor. 0.3 weighs the latest run at 30%, history at 70%.
# High enough to track real shifts in scraper speed within a handful of runs,
# low enough that one outlier (e.g. a Cloudflare-throttled g2 fetch) doesn't
# poison the estimate.
ALPHA = 0.3

DEFAULT_PATH = os.path.expanduser("~/.config/sift/timings.json")

# Seed table — placeholder values rough enough to be plausibly close on a
# cold-start run. They will be overwritten by EMA after the first real run
# that touches each key. The user plans to hand-curate these from their own
# logs before publishing; treat the numbers below as initial seeds, not facts.
SEED_TIMINGS: Dict[str, Dict[str, float]] = {
    "scrape": {
        "reddit": 25.0,
        "g2": 60.0,
        "app_store": 6.0,
        "play_store": 6.0,
        "youtube": 4.0,
        "hacker_news": 5.0,
        "github_issues": 6.0,
        "product_hunt": 8.0,
        "stack_overflow": 5.0,
        "dev_to": 4.0,
        "support_forums": 5.0,
        "changelogs": 5.0,
        "discord_exports": 2.0,
        "linkedin_comments": 2.0,
    },
    "pipeline": {
        "embedding": 5.0,
        "clustering": 1.5,
        "analyse_cluster": 6.0,
        "insights": 9.0,
        "comparison": 12.0,
    },
}


_lock = threading.Lock()
_loaded = False
_cache: Dict[str, Dict[str, float]] = {}
_dirty = False
_path = DEFAULT_PATH


def _load() -> None:
    """Read the JSON store into ``_cache`` on first access."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(_path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for category, entries in data.items():
                if isinstance(entries, dict):
                    _cache[category] = {
                        k: float(v) for k, v in entries.items()
                        if isinstance(v, (int, float)) and v > 0
                    }
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.debug("Could not load timings cache at %s: %s", _path, exc)


def get(category: str, key: str) -> float:
    """Return the EMA-smoothed expected duration, falling back to the seed.

    Always returns a positive float — never raises for an unknown key, because
    the estimator must always have something to drive the curve. New keys
    not present in ``SEED_TIMINGS`` get a neutral 10s default; once a real
    run records a duration, the EMA takes over.
    """
    with _lock:
        _load()
        observed = _cache.get(category, {}).get(key)
        if observed is not None:
            return observed
    seed = SEED_TIMINGS.get(category, {}).get(key)
    if seed is not None:
        return seed
    return 10.0


def record(category: str, key: str, observed: float) -> None:
    """Fold ``observed`` (seconds) into the EMA for ``(category, key)``.

    Marks the cache dirty; the actual write happens lazily in ``flush()``.
    """
    if observed <= 0:
        return
    global _dirty
    with _lock:
        _load()
        bucket = _cache.setdefault(category, {})
        prior = bucket.get(key)
        if prior is None:
            # No prior EMA yet — blend seed with the observed value so a
            # wildly wrong seed gets pulled toward reality on the very first
            # measurement instead of dominating for several runs.
            seed = SEED_TIMINGS.get(category, {}).get(key, observed)
            bucket[key] = ALPHA * observed + (1 - ALPHA) * seed
        else:
            bucket[key] = ALPHA * observed + (1 - ALPHA) * prior
        _dirty = True


def flush() -> None:
    """Persist the in-memory cache to disk. Safe to call multiple times."""
    global _dirty
    with _lock:
        if not _dirty:
            return
        try:
            os.makedirs(os.path.dirname(_path), exist_ok=True)
            tmp = _path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(_cache, f, indent=2, sort_keys=True)
            os.replace(tmp, _path)
            _dirty = False
        except OSError as exc:
            logger.debug("Could not persist timings cache to %s: %s", _path, exc)
