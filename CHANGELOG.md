# Changelog

All notable changes to Sift will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-27

First public release on PyPI as `getsift`.

### Added
- Interactive Rich-based terminal UI (`sift`) with menu navigation, escape-to-exit, and an
  adaptive setup wizard that writes `config.yaml` + `.env`.
- `sift init` first-run setup command that scaffolds config from defaults and prompts for
  required API keys.
- Scripted commands: `sift analyze` and `sift scrape` for automation use.
- Multi-source scrapers behind a common `BaseScraper` interface:
  - G2 (curl_cffi with Playwright fallback, UA rotation, polite delays)
  - Apple App Store reviews (RSS)
  - Google Play Store details/reviews
  - YouTube comments (YouTube Data API)
  - Hacker News (Algolia Search API)
  - GitHub issues (Search API, optional token)
  - Product Hunt comments
  - Stack Overflow, Dev.to
  - Support forums and changelogs via configurable URL templates
  - Discord and LinkedIn comment exports (JSON files / URLs)
  - Reddit (PRAW) — wired up but muted by default until API approval
- Pipeline: hash-based deduplication, relevance gate using product context, sentence
  embeddings (`all-MiniLM-L12-v2`), UMAP + HDBSCAN clustering, LLM cluster analysis, and
  multi-product comparison.
- Token-bucket rate limiter (`RateLimiter`) for HTTP scrapers and `PrawRateMonitor` for
  Reddit, with exponential backoff and jitter.
- OpenAI-compatible LLM client with configurable `base_url` (no vendor lock-in), adaptive
  request parameters that downgrade after provider 400s, and structured JSON parsing with
  fallback to cluster labels.
- Markdown + JSON report output written to `output/`.
- Anonymization at ingestion: usernames are dropped, only source links and review text
  are retained.

### Packaging
- Flat `sift/` package layout for PyPI distribution.
- MIT License.
- Tested on Python 3.11 and 3.12.
- GitHub Actions:
  - `package.yml` runs tests on a 3.11/3.12 matrix, builds the sdist + wheel, smoke-tests
    `sift --help` from the installed wheel, attaches artifacts to GitHub Releases on
    `v*` tags, and publishes to PyPI via trusted publishing on manual dispatch.
  - `qa.yml` runs a CLI QA sweep via Factory Droid.

[0.1.0]: https://github.com/Gitter09/sift/releases/tag/v0.1.0
