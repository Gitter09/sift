"""Offline sitemap-backed search fallback.

When the primary ``SearchClient`` (Brave) is unreachable or has
exhausted its quota, the pipeline can fall through to a local index
built from a site's public sitemap. The first lookup for a given site
downloads the sitemap once, parses ``<loc>`` entries into a SQLite
table, and serves subsequent lookups offline.

Sitemap matching uses a simple lowercase substring + token-overlap
score — good enough for resolver fallback where we already have rich
search context from the cached profile.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from sift.pipeline.http_client import CurlCffiSession
from sift.pipeline.resolver.models import SearchHit
from sift.pipeline.resolver.search.base import SearchClient

logger = logging.getLogger(__name__)

# Per-host sitemap URLs. Sourced from each site's robots.txt /
# documented entry points; verified manually before adding.
_SITEMAP_URLS = {
    "producthunt.com": ["https://www.producthunt.com/sitemap-products.xml.gz"],
    "g2.com": ["https://www.g2.com/sitemap_products.xml"],
}


class SitemapIndex(SearchClient):
    """Search backend backed by per-host sitemap indexes in SQLite."""

    def __init__(self, db_path: str, ttl_days: int = 14):
        self.db_path = str(Path(db_path).expanduser())
        self.ttl = timedelta(days=ttl_days)
        self._http = CurlCffiSession()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def backend_name(self) -> str:
        return "sitemap"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sitemap_entries (
                    host TEXT NOT NULL,
                    url TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    PRIMARY KEY (host, url)
                );
                CREATE TABLE IF NOT EXISTS sitemap_meta (
                    host TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sitemap_slug ON sitemap_entries(host, slug);
                """
            )

    def web_search(self, query: str, limit: int = 10) -> List[SearchHit]:
        # Extract `site:` operator if present.
        host = _extract_site(query)
        if not host:
            return []
        self._ensure_fresh(host)
        tokens = _tokenize(query)
        if not tokens:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, slug FROM sitemap_entries WHERE host = ?",
                (host,),
            ).fetchall()

        scored = []
        for row in rows:
            slug_tokens = set(_tokenize(row["slug"]))
            overlap = len(tokens & slug_tokens)
            if overlap == 0:
                continue
            scored.append((overlap, row["url"], row["slug"]))
        scored.sort(reverse=True, key=lambda x: x[0])

        return [
            SearchHit(url=u, title=slug, snippet="(sitemap match)", rank=i + 1)
            for i, (_, u, slug) in enumerate(scored[:limit])
        ]

    def _ensure_fresh(self, host: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fetched_at FROM sitemap_meta WHERE host = ?", (host,)
            ).fetchone()
        if row:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - fetched_at < self.ttl:
                return
        self._download_and_index(host)

    def _download_and_index(self, host: str) -> None:
        urls = _SITEMAP_URLS.get(host) or []
        if not urls:
            logger.info("No sitemap configured for host '%s'", host)
            return

        entries: list[tuple[str, str, str]] = []
        for sitemap_url in urls:
            try:
                resp = self._http.get(sitemap_url, timeout=30)
                if resp is None or resp.status_code != 200:
                    logger.warning("Sitemap fetch failed for %s", sitemap_url)
                    continue
                content = resp.content
                if sitemap_url.endswith(".gz"):
                    import gzip
                    content = gzip.decompress(content)
                root = ET.fromstring(content)
            except Exception as e:
                logger.warning("Sitemap parse failed for %s: %s", sitemap_url, e)
                continue
            # Strip namespace for forgiving parsing.
            for loc in root.iter():
                if loc.tag.endswith("loc") and loc.text:
                    url = loc.text.strip()
                    slug = _slug_from_url(url)
                    if slug:
                        entries.append((host, url, slug))

        if not entries:
            return

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM sitemap_entries WHERE host = ?", (host,))
            conn.executemany(
                "INSERT OR IGNORE INTO sitemap_entries(host, url, slug) VALUES (?, ?, ?)",
                entries,
            )
            conn.execute(
                "INSERT INTO sitemap_meta(host, fetched_at) VALUES (?, ?)"
                " ON CONFLICT(host) DO UPDATE SET fetched_at = excluded.fetched_at",
                (host, now),
            )
        logger.info("Indexed %d sitemap entries for %s", len(entries), host)


_SITE_PREFIX = re.compile(r"site:([\w.-]+)", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _extract_site(query: str) -> str:
    match = _SITE_PREFIX.search(query)
    if not match:
        return ""
    host = match.group(1).lower().removeprefix("www.")
    # Map a path-qualified site: prefix (`site:g2.com/products`) to its root host.
    return host.split("/", 1)[0]


def _tokenize(value: str) -> set[str]:
    cleaned = _SITE_PREFIX.sub(" ", value).lower()
    return set(_TOKEN_RE.findall(cleaned))


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path
    if not path:
        return ""
    parts = [p for p in path.strip("/").split("/") if p]
    return parts[-1] if parts else ""
