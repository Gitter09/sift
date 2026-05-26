# Sift Documentation

Sift is a CLI-first product research tool for collecting public product feedback, deduplicating it, clustering complaint themes with embeddings plus UMAP and HDBSCAN, and generating AI-assisted product insight reports.

This file is intended to be the complete working documentation source for future developer docs. It covers setup, usage, configuration, architecture, data flow, module responsibilities, testing, extension points, and operational notes.

## Table of Contents

1. [Project Summary](#project-summary)
2. [What Sift Does](#what-sift-does)
3. [How To Access The Tool](#how-to-access-the-tool)
4. [System Requirements](#system-requirements)
5. [Installation And Setup](#installation-and-setup)
6. [Environment Variables](#environment-variables)
7. [Configuration](#configuration)
8. [CLI Usage](#cli-usage)
9. [End-To-End Data Flow](#end-to-end-data-flow)
10. [Supported Data Sources](#supported-data-sources)
11. [Output Files And Report Formats](#output-files-and-report-formats)
12. [Architecture Overview](#architecture-overview)
13. [Source Code Guide](#source-code-guide)
14. [Core Data Models](#core-data-models)
15. [Scraper Architecture](#scraper-architecture)
16. [Pipeline Architecture](#pipeline-architecture)
17. [LLM Integration](#llm-integration)
18. [Rate Limiting And Retry Strategy](#rate-limiting-and-retry-strategy)
19. [Privacy And Deduplication](#privacy-and-deduplication)
20. [Logging And Debugging](#logging-and-debugging)
21. [Testing](#testing)
22. [Adding A New Data Source](#adding-a-new-data-source)
23. [Adding A New Pipeline Step](#adding-a-new-pipeline-step)
24. [Developer Workflow](#developer-workflow)
25. [Known Limitations](#known-limitations)
26. [Troubleshooting](#troubleshooting)
27. [Roadmap](#roadmap)
28. [Architecture Decision Log Requirements](#architecture-decision-log-requirements)

## Project Summary

| Property | Value |
| --- | --- |
| Project name | Sift |
| Package name | `sift` |
| Language | Python 3.11+ |
| Interface | Click-based CLI |
| CLI entry point | `sift`, mapped to `src.cli:main` |
| Development invocation | `python -m src.cli ...` |
| Primary config file | `config.yaml` |
| Secret config | `.env` |
| Test runner | `python -m pytest tests/ -v` |
| Main output directory | `output/` |
| Main dependencies | Click, PRAW, BeautifulSoup, requests, sentence-transformers, UMAP, HDBSCAN, OpenAI SDK, PyYAML, python-dotenv, Rich |

Important naming rule: all user-facing and developer-facing references must use `Sift`. Do not introduce legacy or alternate product names.

## What Sift Does

Sift helps product builders and researchers understand what users complain about across public feedback channels.

At a high level, it:

- Scrapes or ingests feedback from configured product feedback sources.
- Stores each item as an anonymized `FeedbackItem`.
- Removes duplicates using deterministic hash IDs.
- Embeds text with a sentence-transformers model.
- Reduces embedding dimensionality with UMAP.
- Clusters semantically similar complaints with HDBSCAN.
- Uses an OpenAI-compatible LLM endpoint to label clusters, summarize pain points, assign severity, and generate overall insights.
- Compares multiple products when more than one product is analyzed.
- Writes Markdown and JSON reports to disk.

Sift is currently CLI-first. Its internal modules are intentionally separated so the same scraper, pipeline, model, and report code can later be wrapped by a web dashboard or API.

## How To Access The Tool

During local development, the most reliable invocation is:

```bash
python -m src.cli analyze "Notion"
```

After the package is installed in editable mode or installed into the active environment, the configured console script is:

```bash
sift analyze "Notion"
```

The package entry point is defined in `pyproject.toml`:

```toml
[project.scripts]
sift = "src.cli:main"
```

The CLI currently exposes two commands:

- `analyze`: scrape feedback, deduplicate it, cluster it, analyze it with an LLM, and save reports.
- `scrape`: scrape and deduplicate raw feedback only, without embeddings, clustering, LLM analysis, or comparison.

## System Requirements

Sift expects:

- Python 3.11 or newer.
- A working Python virtual environment.
- Network access to configured feedback sources.
- An OpenAI-compatible LLM endpoint for full analysis reports.
- Optional source-specific API credentials for sources such as Reddit, YouTube, and GitHub.

The clustering stack depends on packages that can be heavier to install than ordinary pure-Python packages:

- `sentence-transformers`
- `umap-learn`
- `hdbscan`
- `numpy`
- ML-related transitive dependencies such as PyTorch through sentence-transformers

The first run may download the configured embedding model.

## Installation And Setup

Clone the repository:

```bash
git clone https://github.com/<your-username>/sift.git
cd sift
```

Create and activate a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install Sift with development dependencies:

```bash
pip install -e ".[dev]"
```

Create local environment configuration:

```bash
cp .env.example .env
```

Edit `.env` with the LLM endpoint credentials and any optional source credentials.

Run the tests:

```bash
python -m pytest tests/ -v
```

Run a smoke test:

```bash
python -m src.cli scrape "Linear" --source hacker_news
```

Run a full analysis:

```bash
python -m src.cli analyze "Linear" --source hacker_news
```

For full analysis, Sift needs enough feedback items to cluster. If fewer than 3 unique feedback items are collected for a product, Sift skips analysis for that product.

## Environment Variables

Sift loads `.env` automatically through `python-dotenv` in `src/config.py`.

Supported environment variables:

| Variable | Purpose | Used by |
| --- | --- | --- |
| `LLM_API_KEY` | API key for the OpenAI-compatible LLM endpoint | `LLMConfig` |
| `LLM_BASE_URL` | Base URL for the OpenAI-compatible API | `LLMConfig` |
| `LLM_MODEL` | Model name passed to the LLM endpoint | `LLMConfig` |
| `REDDIT_CLIENT_ID` | Reddit OAuth client ID | `RedditConfig` |
| `REDDIT_CLIENT_SECRET` | Reddit OAuth client secret | `RedditConfig` |
| `YOUTUBE_API_KEY` | YouTube Data API key | `YouTubeConfig` |
| `GITHUB_TOKEN` | Optional GitHub token for higher API limits | `GitHubIssuesConfig` |
| `G2_REQUEST_DELAY` | Overrides configured G2 request delay | `G2Config` |
| `MAX_FEEDBACK_PER_SOURCE` | Caps retained feedback after deduplication in the CLI | `Settings` |

Example:

```env
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
YOUTUBE_API_KEY=optional-youtube-key
GITHUB_TOKEN=optional-github-token
REDDIT_CLIENT_ID=optional-reddit-client-id
REDDIT_CLIENT_SECRET=optional-reddit-client-secret
G2_REQUEST_DELAY=2.5
MAX_FEEDBACK_PER_SOURCE=100
```

Security note: `.env` and `.env.example` are gitignored in this project because local examples may contain real credentials. Do not commit secrets.

## Configuration

The main configuration file is `config.yaml`. It controls source selection, scraper behavior, clustering parameters, LLM defaults, and logging.

Configuration is loaded by:

```python
from src.config import load_settings

settings = load_settings("config.yaml")
```

The loader merges YAML values with environment-variable overrides for secrets and selected runtime values.

### Source Selection

```yaml
sources:
  disabled_sources:
    - "reddit"
  default_sources:
    - "g2"
    - "app_store"
    - "play_store"
    - "youtube"
    - "hacker_news"
    - "github_issues"
    - "product_hunt"
    - "support_forums"
    - "changelogs"
    - "discord_exports"
    - "linkedin_comments"
```

`default_sources` are used when the CLI command does not pass `--source`.

`disabled_sources` always win. If a source is listed as disabled, `get_scraper()` returns `None` even if the source is requested.

Reddit is disabled by default while API approval is pending. To reactivate Reddit later, remove `reddit` from `disabled_sources`, add credentials, and include `reddit` in `default_sources` or pass `--source reddit`.

### Reddit Configuration

```yaml
reddit:
  subreddits:
    - "SaaS"
    - "productivity"
    - "startups"
    - "software"
    - "AskReddit"
  search_sort: "relevance"
  max_posts: 30
  max_comments_per_post: 15
  target_rate_per_minute: 80
  praw_ratelimit_seconds: 300
  subreddit_delay: 2.0
```

Reddit uses PRAW and requires `REDDIT_CLIENT_ID` plus `REDDIT_CLIENT_SECRET`.

### G2 Configuration

```yaml
g2:
  request_delay: 2.5
  max_pages: 5
  user_agent_rotation: true
  max_requests_per_minute: 12
  backoff_base: 2.0
  max_backoff: 60.0
  max_retries: 3
  jitter_range: [0.5, 1.5]
```

G2 has no official API and uses bot protection. Sift therefore uses conservative rate limiting, user-agent rotation, exponential backoff, and jitter.

### App Store Configuration

```yaml
app_store:
  app_ids:
    "Notion": "1232780281"
  countries: ["us"]
  max_pages: 1
  max_items: 50
  request_delay: 1.0
  max_requests_per_minute: 30
```

Product names must match the CLI product argument exactly. If a product has no configured app ID, the source skips cleanly.

### Play Store Configuration

```yaml
play_store:
  package_names:
    "Notion": "notion.id"
  countries: ["us"]
  languages: ["en"]
  max_items: 50
  request_delay: 1.0
  max_requests_per_minute: 20
```

Product names must map to Android package names.

### YouTube Configuration

```yaml
youtube:
  video_ids:
    "Notion":
      - "VIDEO_ID"
  max_videos: 5
  max_comments_per_video: 50
  order: "relevance"
```

YouTube requires `YOUTUBE_API_KEY`. Product names must map to relevant video IDs.

### Hacker News Configuration

```yaml
hacker_news:
  max_items: 50
  tags: "comment,story"
  request_delay: 1.0
  max_requests_per_minute: 30
```

Hacker News uses the public Algolia HN Search API and does not require credentials.

### GitHub Issues Configuration

```yaml
github_issues:
  repos:
    "VS Code":
      - "microsoft/vscode"
  max_items: 50
  request_delay: 1.0
  max_requests_per_minute: 30
```

GitHub uses the GitHub Search API. `GITHUB_TOKEN` is optional but recommended for higher limits.

### Product Hunt Configuration

```yaml
product_hunt:
  slugs:
    "Some Product": "some-product-slug"
  max_items: 50
  request_delay: 2.0
  max_requests_per_minute: 20
```

If no slug is configured, Sift derives one by lowercasing the product name and replacing spaces with hyphens.

### Support Forums Configuration

```yaml
support_forums:
  search_urls:
    - "https://community.example.com/search?q={query}"
  max_items: 50
  request_delay: 1.0
  max_requests_per_minute: 20
```

URL templates may use `{query}` or `{product}`. Both are URL-encoded versions of the product name.

### Changelogs Configuration

```yaml
changelogs:
  urls:
    "Linear":
      - "https://linear.app/changelog"
  search_urls: []
  max_items: 50
  request_delay: 1.0
  max_requests_per_minute: 20
```

Changelog ingestion can use direct product URL mappings and optional search URL templates.

### Discord Export Configuration

```yaml
discord_exports:
  paths:
    - "exports/discord.json"
  urls: []
  max_items: 100
```

Discord is not scraped directly. Sift ingests public or exported JSON files and URLs.

### LinkedIn Comment Export Configuration

```yaml
linkedin_comments:
  paths:
    - "exports/linkedin-comments.json"
  urls: []
  max_items: 100
```

LinkedIn is not scraped directly. Sift ingests public or exported JSON files and URLs.

### Clustering Configuration

```yaml
clustering:
  embedding_model: "all-MiniLM-L12-v2"
  umap_n_neighbors: 15
  umap_n_components: 5
  hdbscan_min_cluster_size: 3
  hdbscan_min_samples: 1
```

`embedding_model` is passed to `SentenceTransformer`.

UMAP reduces high-dimensional text embeddings before HDBSCAN clusters them. HDBSCAN allows Sift to discover cluster count automatically and ignore noise.

### LLM Configuration

```yaml
llm:
  model: "gpt-4o-mini"
  temperature: 0.3
  max_tokens: 2000
```

`LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` can override YAML values through `.env`.

The LLM client uses the OpenAI Python SDK against a configurable `base_url`, so any OpenAI-compatible endpoint can be used.

### Logging Configuration

```yaml
logging:
  level: "INFO"
  format: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
```

The CLI configures logging through `setup_logging(settings, verbose=...)`. Passing `--verbose` sets the `src` logger to `DEBUG`.

## CLI Usage

All examples can be run either through `python -m src.cli` or the installed `sift` command.

### Analyze One Product

```bash
python -m src.cli analyze "Linear"
```

This command:

1. Loads settings.
2. Resolves default sources.
3. Scrapes feedback for `Linear`.
4. Deduplicates feedback.
5. Skips analysis if fewer than 3 unique items were collected.
6. Generates embeddings.
7. Clusters feedback.
8. Uses the LLM to label and summarize clusters.
9. Generates overall insights.
10. Saves Markdown and JSON reports.

### Analyze Multiple Products

```bash
python -m src.cli analyze "Figma" "Sketch" "Penpot"
```

Each product is scraped, deduplicated, embedded, clustered, and analyzed independently. If at least two product reports are generated, Sift also runs a multi-product comparison.

### Analyze With Specific Sources

```bash
python -m src.cli analyze "Slack" --source g2
python -m src.cli analyze "VS Code" --source github_issues --source hacker_news
```

`--source` can be passed multiple times. Unknown sources are reported and ignored. Disabled sources are skipped by the scraper factory.

### Use A Custom Config File

```bash
python -m src.cli analyze "Notion" --config path/to/config.yaml
```

### Write Reports To A Custom Output Directory

```bash
python -m src.cli analyze "Notion" --output reports
```

### Enable Verbose Logging

```bash
python -m src.cli analyze "Notion" --verbose
```

The `--verbose` flag is defined on both the root Click group and individual commands.

### Scrape Only

```bash
python -m src.cli scrape "Notion" --source g2 --source app_store
```

The `scrape` command collects and deduplicates feedback, then saves raw JSON:

```text
output/notion_raw.json
```

It does not run embeddings, clustering, LLM analysis, product reports, or comparison reports.

## End-To-End Data Flow

```text
CLI command
  |
  v
load_settings(config.yaml + .env)
  |
  v
resolve sources
  |
  v
get_scraper(source, settings)
  |
  v
scraper.scrape(product)
  |
  v
List[FeedbackItem]
  |
  v
DedupFilter
  |
  v
Embedder with SentenceTransformer
  |
  v
UMAP dimensionality reduction
  |
  v
HDBSCAN clustering
  |
  v
Analyzer LLM cluster labels, summaries, severity
  |
  v
Analyzer LLM overall product insights
  |
  v
ProductReport
  |
  +--> if multiple products: Comparator LLM comparison
  |
  v
Markdown and JSON reports in output/
```

Important behavior:

- Feedback is deduplicated per CLI command execution.
- Products with fewer than 3 unique items are skipped for analysis.
- If all products are skipped, no reports are generated.
- If exactly one product report exists, Sift still writes a comparison report with a single-product fallback message.
- If two or more product reports exist, Sift asks the LLM for shared pain points, unique pain points, and competitive insights.

## Supported Data Sources

Sift currently recognizes the following source keys:

- `reddit`
- `g2`
- `app_store`
- `play_store`
- `youtube`
- `hacker_news`
- `github_issues`
- `product_hunt`
- `support_forums`
- `changelogs`
- `discord_exports`
- `linkedin_comments`

These source keys are registered in `src/scrapers/factory.py` as `AVAILABLE_SOURCES`.

### G2

Class: `G2Scraper`

File: `src/scrapers/g2.py`

Method:

- Builds or discovers a product URL.
- Fetches `/reviews?page=N`.
- Parses review elements with BeautifulSoup.
- Extracts review text and rating when available.
- Stops when no review elements are found, a fetch fails, `max_pages` is reached, or 50 items are collected.

Rate limiting:

- Token-bucket style interval limiter.
- User-agent rotation.
- Exponential backoff on 429 and 403.
- Retries controlled by `max_retries`.

Requirements:

- No API key required.
- Network access to G2.

### Reddit

Class: `RedditScraper`

File: `src/scrapers/reddit.py`

Method:

- Uses PRAW.
- Searches configured subreddits for the product name.
- Collects post title plus selftext.
- Collects up to `max_comments_per_post` comments per post.
- Stores Reddit post and comment URLs.
- Stores metadata such as subreddit, Reddit ID, score, and comment count.

Rate limiting:

- PRAW `ratelimit_seconds` is set from config.
- `PrawRateMonitor` tracks approximate request pace.
- Target rate defaults to 80 requests per minute.
- Subreddit switching delay defaults to 2 seconds.

Requirements:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- Reddit must be removed from `disabled_sources`.

### App Store

Class: `AppStoreScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Uses Apple customer reviews RSS JSON endpoint.
- Requires product-to-app-ID mapping.
- Iterates configured countries and pages.
- Extracts title, content, rating, and review URL.

Requirements:

- `app_store.app_ids` mapping in `config.yaml`.

### Play Store

Class: `PlayStoreScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Fetches the public Google Play app details page with `showAllReviews=true`.
- Requires product-to-package-name mapping.
- Parses HTML elements with `data-review-id`.

Requirements:

- `play_store.package_names` mapping in `config.yaml`.

### YouTube Comments

Class: `YouTubeScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Uses YouTube Data API `commentThreads`.
- Requires product-to-video-ID mapping.
- Collects top-level comments.
- Stores video ID and like count in metadata.

Requirements:

- `YOUTUBE_API_KEY`
- `youtube.video_ids` mapping in `config.yaml`.

### Hacker News

Class: `HackerNewsScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Uses Algolia HN Search API.
- Searches for product name with configured tags.
- Extracts comment text, story title, title, object ID, points, and creation date.

Requirements:

- No API key required.

### GitHub Issues

Class: `GitHubIssuesScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Uses GitHub Search API.
- Requires product-to-repo mapping.
- Searches `repo:{owner/repo} {product_name} is:issue`.
- Extracts issue title, body, state, comments count, URL, and date.

Requirements:

- `github_issues.repos` mapping in `config.yaml`.
- Optional `GITHUB_TOKEN`.

### Product Hunt

Class: `ProductHuntScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Fetches Product Hunt product page.
- Uses configured slug or derived slug.
- Parses comment-like elements.
- Keeps text that includes the product name.

Requirements:

- Optional `product_hunt.slugs` mapping if the derived slug is not correct.

### Support Forums

Class: `SupportForumsScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Uses configured search URL templates.
- Fetches HTML pages.
- Parses common content selectors such as `article`, `main p`, `.post`, `.topic`, `.comment`, and `li`.
- Keeps text that includes the product name.

Requirements:

- `support_forums.search_urls` configured.

### Changelogs

Class: `ChangelogScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Fetches product-specific changelog URLs.
- Parses common content selectors.
- Optionally falls back to configured search URL templates.

Requirements:

- `changelogs.urls` and/or `changelogs.search_urls`.

### Discord Exports

Class: `DiscordExportsScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Ingests JSON records from configured local paths or URLs.
- Accepts either a list of records or dictionaries with `messages` or `comments`.
- Extracts text from `content`, `text`, `body`, or `comment`.
- Keeps records whose text mentions the product name.

Requirements:

- Public or exported JSON path or URL.
- No direct Discord scraping.

### LinkedIn Comment Exports

Class: `LinkedInCommentsScraper`

File: `src/scrapers/simple_sources.py`

Method:

- Same export ingestion mechanism as Discord exports.
- Ingests public or exported JSON records from configured paths or URLs.

Requirements:

- Public or exported JSON path or URL.
- No direct LinkedIn scraping.

## Output Files And Report Formats

Sift writes reports to the configured output directory, `output/` by default.

### Analyze Output

For each product:

```text
output/{product_slug}_{timestamp}.md
output/{product_slug}_{timestamp}.json
```

For the comparison:

```text
output/comparison_{timestamp}.md
output/comparison_{timestamp}.json
```

The timestamp format is:

```text
YYYYMMDD_HHMMSS
```

Product slugs are currently generated by lowercasing the product name and replacing spaces with underscores.

### Scrape Output

The scrape-only command writes:

```text
output/{product_slug}_raw.json
```

### Product Markdown Report Contents

Generated by `generate_markdown_report()`:

- Title: `Product Feedback Analysis: {product}`
- Generation timestamp
- Total feedback collected
- Overall insights
- Top pain points
- Clustered complaint themes
- Severity badge
- Severity value
- Cluster summary
- Representative quotes

### Comparison Markdown Report Contents

Generated by `generate_comparison_markdown()`:

- Title: `Competitive Product Comparison`
- Product list
- Generation timestamp
- Competitive insights
- Shared pain points
- Unique pain points by product
- Individual product report summaries

### JSON Report Structure

Product report JSON mirrors `ProductReport.to_dict()`:

```json
{
  "product": "Notion",
  "total_feedback_count": 10,
  "clusters": [],
  "overall_insights": "Summary text",
  "top_pain_points": ["Pain point"]
}
```

Comparison report JSON mirrors `ComparisonReport.to_dict()`:

```json
{
  "products": ["Notion", "Obsidian"],
  "product_reports": {},
  "shared_pain_points": [],
  "unique_pain_points": {},
  "competitive_insights": "Summary text"
}
```

## Architecture Overview

Repository structure:

```text
src/
  cli.py                         Click CLI entry point
  config.py                      YAML and environment configuration loader
  models/
    feedback.py                  FeedbackItem dataclass
    cluster.py                   ClusterResult dataclass
    report.py                    ProductReport and ComparisonReport dataclasses
  scrapers/
    base.py                      BaseScraper abstract class
    factory.py                   Source registry and scraper construction
    g2.py                        G2 scraper
    reddit.py                    Reddit scraper
    simple_sources.py            App Store, Play Store, YouTube, HN, GitHub, Product Hunt, forums, changelogs, exports
  pipeline/
    dedup.py                     Cross-source deduplication
    embedder.py                  SentenceTransformer embedding wrapper
    clusterer.py                 UMAP + HDBSCAN clustering
    analyzer.py                  LLM cluster and product analysis
    comparator.py                LLM multi-product comparison
    report_generator.py          Markdown and JSON report generation
    rate_limiter.py              Generic HTTP and PRAW rate limiting helpers
  ui/
    display.py                   Rich display helpers, currently separate from core CLI flow
tests/
  test_config.py
  test_dedup.py
  test_models.py
  test_pipeline.py
  test_rate_limiter.py
  test_scrapers.py
```

Design principles:

- CLI is thin orchestration.
- Scrapers return only `FeedbackItem` objects.
- Pipeline steps operate on models, not CLI details.
- Config flows through `src/config.py`.
- LLM access uses an OpenAI-compatible SDK and configurable `base_url`.
- Reports are generated in both Markdown and JSON.
- Scrapers apply rate limiting.
- New data sources should not require changes to embedding, clustering, analysis, or reporting code.

## Source Code Guide

### `src/cli.py`

Defines the Click CLI.

Main group:

```python
@click.group()
def main(ctx, verbose):
    """Sift - scrape, cluster, and analyze product feedback."""
```

Commands:

- `analyze`
- `scrape`

Important functions:

- `analyze(ctx, products, source, config, output, verbose)`
- `scrape_cmd(ctx, product, source, config, output, verbose)`
- `_resolve_sources(source, settings)`

`analyze` is the full pipeline orchestrator. `scrape_cmd` is raw ingestion only.

### `src/config.py`

Defines all configuration dataclasses and the loader.

Important dataclasses:

- `SourcesConfig`
- `RedditConfig`
- `G2Config`
- `AppStoreConfig`
- `PlayStoreConfig`
- `YouTubeConfig`
- `HackerNewsConfig`
- `GitHubIssuesConfig`
- `ProductHuntConfig`
- `SupportForumsConfig`
- `ChangelogsConfig`
- `DiscordExportsConfig`
- `LinkedInCommentsConfig`
- `ClusteringConfig`
- `LLMConfig`
- `LoggingConfig`
- `Settings`

Important functions:

- `load_settings(config_path="config.yaml")`
- `setup_logging(settings, verbose=False)`

### `src/scrapers/base.py`

Defines the scraper contract:

```python
class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, product_name: str) -> List[FeedbackItem]:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass
```

Every scraper must implement this interface.

### `src/scrapers/factory.py`

Defines:

- `AVAILABLE_SOURCES`
- `get_scraper(source, settings)`
- `get_all_scrapers(settings)`
- `default_sources(settings)`

The factory is the central source registry.

### `src/scrapers/g2.py`

Contains:

- `USER_AGENTS`
- `G2Scraper`

Handles G2-specific URL discovery, review parsing, rate limiting, retries, and anti-bot-safe request pacing.

### `src/scrapers/reddit.py`

Contains:

- `RedditScraper`

Uses PRAW and `PrawRateMonitor`.

### `src/scrapers/simple_sources.py`

Contains shared request helpers and simpler source adapters:

- `RequestsScraper`
- `AppStoreScraper`
- `PlayStoreScraper`
- `YouTubeScraper`
- `HackerNewsScraper`
- `GitHubIssuesScraper`
- `ProductHuntScraper`
- `SearchPageScraper`
- `SupportForumsScraper`
- `ChangelogScraper`
- `JsonExportScraper`
- `DiscordExportsScraper`
- `LinkedInCommentsScraper`

Also contains helper functions:

- `_safe_float(value)`
- `_parse_datetime(value)`
- `_html_to_text(value)`

### `src/pipeline/dedup.py`

Contains:

- `DedupFilter`

Tracks seen feedback IDs and filters duplicates across sources and across repeated calls in the same process.

### `src/pipeline/embedder.py`

Contains:

- `Embedder`

Wraps `SentenceTransformer`. Returns normalized embeddings.

### `src/pipeline/clusterer.py`

Contains:

- `Clusterer`

Runs UMAP followed by HDBSCAN. Returns a list of non-noise `ClusterResult` objects sorted by size. Representative quotes are selected from the longest item texts in each non-noise cluster.

### `src/pipeline/analyzer.py`

Contains:

- `Analyzer`
- `ANALYZE_CLUSTER_PROMPT`
- `OVERALL_INSIGHTS_PROMPT`

Responsible for LLM cluster labeling, summaries, severity, and overall product insights.

### `src/pipeline/comparator.py`

Contains:

- `Comparator`
- `COMPARISON_PROMPT`

Responsible for multi-product comparison.

### `src/pipeline/report_generator.py`

Contains:

- `generate_markdown_report(report)`
- `generate_comparison_markdown(report)`
- `save_reports(product_reports, comparison_report, output_dir="output")`

Writes both Markdown and JSON files.

### `src/pipeline/rate_limiter.py`

Contains:

- `RateLimiter`
- `PrawRateMonitor`

`RateLimiter` is used by HTTP scrapers. `PrawRateMonitor` is used by the Reddit scraper.

### `src/ui/display.py`

Contains Rich-powered display helpers:

- Banner printing
- Config summary panel
- Progress bars
- Cluster summary tables
- Comparison summary panels
- Report previews
- Done banner
- Warning helpers

The current CLI mostly uses `click.echo()` directly, but this module provides a richer display layer for future CLI polish.

## Core Data Models

### `FeedbackItem`

Defined in `src/models/feedback.py`.

Fields:

| Field | Type | Description |
| --- | --- | --- |
| `source` | `str` | Source key such as `g2`, `hacker_news`, or `github_issues` |
| `product` | `str` | Product name being analyzed |
| `text` | `str` | Feedback text |
| `rating` | `Optional[float]` | Numeric rating if available |
| `url` | `Optional[str]` | Link to original public source |
| `date` | `Optional[datetime]` | Posted date if available |
| `metadata` | `dict` | Source-specific metadata |
| `id` | `str` | Deterministic 16-character hash ID |

The ID is generated in `__post_init__()`:

```python
raw = f"{self.source}:{self.url or self.text}"
self.id = hashlib.sha256(raw.encode()).hexdigest()[:16]
```

This means:

- Same source and same URL produce the same ID, even if text differs.
- Same source and no URL fall back to text hashing.
- Different sources with the same URL do not collide because source is part of the hash input.

`FeedbackItem` intentionally does not store usernames or authors.

### `ClusterResult`

Defined in `src/models/cluster.py`.

Fields:

| Field | Type | Description |
| --- | --- | --- |
| `cluster_id` | `int` | HDBSCAN label. `-1` means noise |
| `label` | `Optional[str]` | Human-readable cluster name from LLM |
| `items` | `List[FeedbackItem]` | Feedback items in cluster |
| `summary` | `Optional[str]` | LLM pain point summary |
| `severity` | `Optional[str]` | `high`, `medium`, or `low` |
| `representative_quotes` | `List[str]` | Short representative snippets |

Computed properties:

- `size`: number of items.
- `is_noise`: whether `cluster_id == -1`.

### `ProductReport`

Defined in `src/models/report.py`.

Fields:

- `product`
- `total_feedback_count`
- `clusters`
- `overall_insights`
- `top_pain_points`

### `ComparisonReport`

Defined in `src/models/report.py`.

Fields:

- `products`
- `product_reports`
- `shared_pain_points`
- `unique_pain_points`
- `competitive_insights`

## Scraper Architecture

All scrapers must implement `BaseScraper`:

```python
def scrape(self, product_name: str) -> List[FeedbackItem]

@property
def source_name(self) -> str
```

Scrapers should:

- Return a list of `FeedbackItem`.
- Avoid storing usernames or direct personal identifiers.
- Include a public URL when available.
- Include useful source-specific metadata.
- Apply rate limiting.
- Catch source-specific recoverable failures where appropriate.
- Log diagnostics with `logging`, not `print()`.
- Avoid hardcoded secrets or config values.

Scrapers should not:

- Run embeddings.
- Run clustering.
- Call the LLM.
- Generate reports.
- Deduplicate globally.
- Write output files.

Source-specific deduplication is unnecessary because global deduplication happens through `DedupFilter`.

## Pipeline Architecture

The pipeline is composed of independent classes:

1. `DedupFilter`
2. `Embedder`
3. `Clusterer`
4. `Analyzer`
5. `Comparator`
6. `report_generator`

### Deduplication

`DedupFilter.filter(items)` returns only unseen items and updates its internal seen set.

The CLI currently creates one `DedupFilter` per command execution, then reuses it across products. This means duplicate IDs are suppressed across the run.

### Embedding

`Embedder.embed(items)`:

- Extracts `item.text`.
- Calls `SentenceTransformer(config.embedding_model)`.
- Uses `model.encode(..., normalize_embeddings=True)`.
- Returns a NumPy array.

Default model:

```text
all-MiniLM-L12-v2
```

### Clustering

`Clusterer.cluster(embeddings, items)`:

- If fewer than 3 items are provided, returns a single cluster with `cluster_id=0`.
- Otherwise, reduces embeddings with UMAP.
- Clusters reduced vectors with HDBSCAN.
- Builds `ClusterResult` objects.
- Skips the noise cluster from returned results.
- Logs how many items were classified as noise.
- Sorts clusters by descending size.

Default UMAP:

- `n_neighbors=15`
- `n_components=5`
- `metric="cosine"`
- `random_state=42`

Default HDBSCAN:

- `min_cluster_size=3`
- `min_samples=1`
- `metric="euclidean"`
- `cluster_selection_method="eom"`

### Analysis

`Analyzer.analyze_clusters(clusters)` labels and summarizes each cluster.

`Analyzer.generate_overall_insights(product, clusters)` generates product-level insights.

If an LLM call or JSON parse fails:

- Cluster analysis falls back to `Cluster {cluster_id}`.
- Cluster summary becomes `Analysis unavailable - LLM call failed`.
- Cluster severity defaults to `medium`.
- Overall insights fall back to `Analysis unavailable - LLM call failed`.
- Top pain points fall back to the first cluster labels.

### Comparison

`Comparator.compare(reports)` compares multiple `ProductReport` objects.

If LLM comparison fails:

- It computes a basic fallback using cluster label set intersection.
- Shared pain points are labels common to all products.
- Unique pain points are labels not in the shared set.
- Competitive insights become `Comparison analysis unavailable (LLM call failed)`.

## LLM Integration

Sift uses the OpenAI Python SDK:

```python
from openai import OpenAI

client = OpenAI(
    api_key=config.api_key,
    base_url=config.base_url,
)
```

This allows any OpenAI-compatible endpoint.

LLM calls use chat completions:

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=[{"role": "user", "content": prompt}],
    temperature=self.temperature,
    max_tokens=self.max_tokens,
)
```

Prompts request strict JSON output. The parser strips Markdown code fences if present before calling `json.loads()`.

LLM-dependent features:

- Cluster labels
- Cluster summaries
- Cluster severity
- Product-level overall insights
- Top pain points
- Multi-product comparison

Sift has fallbacks for LLM failures, but full report quality depends on the LLM response.

## Rate Limiting And Retry Strategy

Rate limiting is centralized in `src/pipeline/rate_limiter.py`.

### `RateLimiter`

Used by HTTP-based scrapers.

Features:

- Minimum interval based on `max_requests_per_minute`.
- Jitter applied to request timing.
- Thread lock around timing state.
- Exponential backoff with jitter.
- Retry eligibility through `should_retry(attempt)`.

Backoff formula:

```text
delay = min(backoff_base ** attempt, max_backoff)
backoff_delay = delay * random(0.8, 1.2)
```

### `PrawRateMonitor`

Used by the Reddit scraper.

Features:

- Tracks approximate request count.
- Logs current request rate every 10 requests at debug level.
- Sleeps proportionally if the current rate exceeds target rate.

### G2 Strategy

G2 is treated as a bot-protected source:

- Default max requests per minute: 12.
- Default request delay: 2.5 seconds.
- User-agent rotation enabled.
- 429 and 403 trigger warning logs and backoff.
- Max retries default to 3.

### Reddit Strategy

Reddit is treated as API-based but rate-limited:

- PRAW handles Reddit headers internally.
- `ratelimit_seconds=300` allows PRAW to wait up to 5 minutes.
- Sift targets 80 requests per minute, below Reddit's typical OAuth allowance.

## Privacy And Deduplication

Sift is intentionally PII-free at ingestion.

Privacy behavior:

- No usernames are stored.
- `FeedbackItem` has no `author` field.
- Original public URL may be stored for traceability.
- Source-specific metadata should not include personal identifiers unless there is a deliberate, documented reason.

Deduplication behavior:

- Each `FeedbackItem` gets a deterministic hash ID.
- Hash input is `source:url` when URL exists.
- Hash input is `source:text` when URL does not exist.
- `DedupFilter` removes repeated IDs.

This gives stable deduplication across sources and repeated scraper calls while preserving source separation.

## Logging And Debugging

Sift uses Python's `logging` module for diagnostics and Click output for user-facing progress.

Logging setup:

```python
setup_logging(settings, verbose=verbose)
```

Default level comes from `config.yaml`:

```yaml
logging:
  level: "INFO"
```

Verbose mode:

```bash
python -m src.cli analyze "Notion" --verbose
```

This sets the `src` logger to `DEBUG`.

Expected logging style:

- Use `logger.debug()` for detailed diagnostics.
- Use `logger.info()` for high-level internal events.
- Use `logger.warning()` for recoverable source issues.
- Use `logger.error()` for failed operations without stack traces.
- Use `logger.exception()` inside exception handlers when stack traces are useful.
- Use `click.echo()` for CLI progress messages.

Do not use `print()` in production code.

## Testing

Run all tests:

```bash
python -m pytest tests/ -v
```

Current test files:

| File | Coverage |
| --- | --- |
| `tests/test_config.py` | Settings defaults, YAML loading, env overrides, logging setup |
| `tests/test_dedup.py` | Dedup filter uniqueness, duplicate filtering, cross-call state, reset, source separation |
| `tests/test_models.py` | Model serialization, deterministic feedback IDs, anonymity, cluster/report properties |
| `tests/test_pipeline.py` | Embedding shape and normalization, clustering behavior, too-few-items fallback |
| `tests/test_rate_limiter.py` | Retry policy, backoff timing, interval waiting, PRAW pacing |
| `tests/test_scrapers.py` | Scraper source names, factory behavior, default Reddit disabling, Reddit reactivation |

When adding a new feature, add corresponding tests.

Testing guidance:

- Mock network calls for scraper behavior where possible.
- Avoid requiring live credentials in unit tests.
- Keep LLM calls mocked in tests.
- For new config fields, test defaults and YAML loading.
- For new models, test `to_dict()`.
- For new source registry entries, test `get_scraper()` and default/disabled behavior.

## Adding A New Data Source

To add a new source, follow these steps.

### 1. Add Configuration

Add a dataclass in `src/config.py`:

```python
@dataclass
class TrustpilotConfig:
    max_items: int = 50
    request_delay: float = 1.0
    max_requests_per_minute: int = 20
```

Add it to `Settings`:

```python
trustpilot: TrustpilotConfig = field(default_factory=TrustpilotConfig)
```

Load it in `load_settings()` from YAML.

Add a section to `config.yaml`:

```yaml
trustpilot:
  max_items: 50
  request_delay: 1.0
  max_requests_per_minute: 20
```

If the source should run by default, add its source key to `sources.default_sources`.

### 2. Implement The Scraper

Create a scraper that implements `BaseScraper`:

```python
from typing import List
from src.models.feedback import FeedbackItem
from src.scrapers.base import BaseScraper

class TrustpilotScraper(BaseScraper):
    def __init__(self, config):
        self.config = config

    @property
    def source_name(self) -> str:
        return "trustpilot"

    def scrape(self, product_name: str) -> List[FeedbackItem]:
        return []
```

Use `RateLimiter` for HTTP requests.

### 3. Register The Source

Update `src/scrapers/factory.py`:

```python
AVAILABLE_SOURCES = {
    ...
    "trustpilot",
}
```

Add construction logic:

```python
elif source == "trustpilot":
    return TrustpilotScraper(settings.trustpilot)
```

### 4. Add Tests

Add tests for:

- Source name.
- Factory construction.
- Disabled-source behavior if relevant.
- Config defaults.
- YAML loading.
- Parsing behavior with mocked responses or fixture HTML/JSON.

### 5. Update Documentation

Update:

- `README.md` if user-facing setup changes.
- `documentation.md`.
- `ARCHITECTURE.md` if this is a significant source or design decision.

## Adding A New Pipeline Step

Pipeline steps should be independent classes or functions under `src/pipeline/`.

Good pipeline step design:

- Accepts model objects or primitive data.
- Returns model objects or primitive data.
- Does not read CLI arguments directly.
- Does not hardcode configuration.
- Does not write files unless it is specifically an output step.
- Is testable without live network access.

If adding a significant step, update the CLI orchestration in `src/cli.py` and document the decision in `ARCHITECTURE.md`.

Examples of future pipeline steps:

- Sentiment scoring
- Language detection
- Spam filtering
- PII redaction beyond current author omission
- Trend detection across scheduled runs
- Alert generation

## Developer Workflow

Recommended local workflow:

```bash
source .venv/bin/activate
python -m pytest tests/ -v
python -m src.cli scrape "Linear" --source hacker_news --verbose
python -m src.cli analyze "Linear" --source hacker_news --verbose
```

Before changing behavior:

1. Read the relevant module.
2. Check existing tests.
3. Check `ARCHITECTURE.md` for prior decisions.
4. Keep changes scoped.
5. Add or update tests.
6. Update `documentation.md` and possibly `README.md`.
7. Add an architecture decision if the change is significant.

Code style conventions:

- Use existing project patterns.
- Use dataclasses for simple structured models and config.
- Use `logging`, not `print()`.
- Keep scraper-specific behavior inside scraper modules.
- Keep pipeline behavior source-agnostic.
- Keep config in `src/config.py` and `config.yaml`.
- Keep secrets in `.env`.
- Use OpenAI-compatible LLM access with configurable `base_url`.
- Preserve PII-free ingestion.

## Known Limitations

Current limitations:

- Reddit is disabled by default pending API approval.
- Some source adapters rely on public HTML structure and may break if sites change markup.
- G2 scraping can be blocked by Cloudflare or Akamai.
- Product names must exactly match config mappings for sources such as App Store, Play Store, YouTube, and GitHub issues.
- The CLI skips analysis for products with fewer than 3 unique feedback items.
- HDBSCAN may classify some feedback as noise; noise is logged but not included in returned clusters.
- The current `DedupFilter` state is in-memory only.
- The LLM output parser expects valid JSON after optional Markdown fence stripping.
- Rich UI helpers exist but are not fully wired into the current CLI flow.
- There is no web dashboard yet.
- There is no scheduled monitoring mode yet.

## Troubleshooting

### `sift` Command Not Found

Install the package into the active environment:

```bash
pip install -e ".[dev]"
```

Or run the CLI directly:

```bash
python -m src.cli analyze "Notion"
```

### No Reports Generated

Likely cause: fewer than 3 unique feedback items were collected for every product.

Try:

```bash
python -m src.cli scrape "Product Name" --source hacker_news --verbose
```

Then inspect the raw output file in `output/`.

### Source Skips Without Error

Some sources require product-specific configuration.

Check:

- `app_store.app_ids`
- `play_store.package_names`
- `youtube.video_ids`
- `github_issues.repos`
- `support_forums.search_urls`
- `changelogs.urls`
- `discord_exports.paths` or `discord_exports.urls`
- `linkedin_comments.paths` or `linkedin_comments.urls`

Also check whether the source is listed in `sources.disabled_sources`.

### Reddit Does Not Run

Reddit is disabled by default.

To enable:

1. Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` to `.env`.
2. Remove `reddit` from `sources.disabled_sources`.
3. Add `reddit` to `sources.default_sources` or pass `--source reddit`.

### YouTube Does Not Run

YouTube requires:

- `YOUTUBE_API_KEY`
- Product video IDs in `youtube.video_ids`

### GitHub Issues Returns Few Or No Results

Check:

- The product name matches the key in `github_issues.repos`.
- Repos are configured as `owner/repo`.
- `GITHUB_TOKEN` is set if unauthenticated rate limits are too low.

### G2 Returns 403 Or 429

G2 may be blocking or throttling requests.

Options:

- Increase `g2.request_delay`.
- Lower `g2.max_requests_per_minute`.
- Keep `user_agent_rotation` enabled.
- Reduce `g2.max_pages`.
- Try again later.

### LLM Analysis Fails

Check:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- Endpoint compatibility with OpenAI chat completions.
- Network access to the endpoint.

Run with verbose logging:

```bash
python -m src.cli analyze "Notion" --source hacker_news --verbose
```

If the LLM call fails, Sift still produces fallback labels where possible.

### Embedding Model Download Is Slow

The first run may download the sentence-transformers model. Subsequent runs should use the local cache.

### HDBSCAN Or UMAP Installation Fails

These packages may require compiled dependencies. Confirm Python version and package build support for the current platform.

Try upgrading packaging tools:

```bash
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

## Roadmap

Current roadmap items:

- Reactivate Reddit source after API approval.
- Add a web app with dashboard UI.
- Add continuous monitoring mode for scheduled runs and sentiment tracking over time.
- Add additional review sites such as Trustpilot, Product Hunt improvements, Capterra, and similar public feedback channels.
- Add Slack or email alerts for new complaint spikes.

## Architecture Decision Log Requirements

This project has a strict architecture decision documentation rule.

Whenever a significant decision affects architecture, data flow, error handling, rate limiting, scraper design, pipeline behavior, security, or user-facing behavior, add a new numbered entry to `ARCHITECTURE.md`.

Use this exact format:

```markdown
## Decision NNN: [Short Title]

**Date:** YYYY-MM-DD
**Context:** [What situation or problem triggered this decision]
**Decision:** [What you decided to do]
**Why:** [The reasoning behind the decision]
**LinkedIn Angle:** [A one-sentence hook that can be repurposed into a LinkedIn post]
```

Rules:

- Numbering must be sequential.
- Check the latest decision number and increment it.
- `LinkedIn Angle` is required.
- When unsure whether a decision is significant enough, document it.

Examples of significant decisions:

- Adding a new data source.
- Changing rate limits or retry behavior.
- Changing LLM provider behavior.
- Changing clustering algorithms.
- Changing report output structure.
- Changing privacy or deduplication behavior.
- Deciding not to implement a feature for a specific reason.

## Quick Reference

Install:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest tests/ -v
```

Analyze:

```bash
python -m src.cli analyze "Product Name"
```

Analyze with selected sources:

```bash
python -m src.cli analyze "Product Name" --source hacker_news --source github_issues
```

Scrape only:

```bash
python -m src.cli scrape "Product Name" --source hacker_news
```

Verbose mode:

```bash
python -m src.cli analyze "Product Name" --verbose
```

Installed command:

```bash
sift analyze "Product Name"
```
