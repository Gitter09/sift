import os

from sift.pipeline.numba_cache import ensure_numba_cache_dir


def test_ensure_numba_cache_dir_sets_writable_default(monkeypatch):
    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)

    cache_dir = ensure_numba_cache_dir()

    assert os.environ["NUMBA_CACHE_DIR"] == cache_dir
    assert cache_dir.endswith("sift-numba-cache")
    assert os.path.isdir(cache_dir)
    assert os.access(cache_dir, os.W_OK)


def test_ensure_numba_cache_dir_preserves_existing_value(monkeypatch, tmp_path):
    custom_cache = tmp_path / "numba"
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(custom_cache))

    cache_dir = ensure_numba_cache_dir()

    assert cache_dir == str(custom_cache)
    assert os.environ["NUMBA_CACHE_DIR"] == str(custom_cache)
    assert custom_cache.is_dir()
