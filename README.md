# Sift

> Scrape user feedback from public product channels, cluster complaints with ML, and generate AI-powered product insights — all from your terminal.

## What It Does

- **Scrapes** G2, app stores, YouTube, Hacker News, GitHub issues, Product Hunt, forums, changelogs, and public exports for real user feedback about any product
- **Anonymizes** reviews at ingestion — no usernames stored, only a clickable link to the source
- **Deduplicates** feedback across sources using hash-based IDs so you never count the same review twice
- **Clusters** complaints and pain points using sentence embeddings + UMAP + HDBSCAN
- **Analyzes** each cluster with an LLM to name themes, summarize issues, and rate severity
- **Compares** multiple products to surface shared vs. unique pain points

## How It Works

```
G2 / App Stores / YouTube / HN / GitHub / Forums / Exports
          │
          └──> Feedback Items ──> Dedup Filter ──> Sentence Embeddings ──> UMAP + HDBSCAN
                       (anonymized)                                      (all-MiniLM-L12-v2)

                                          ┌── Clustered Themes ──> LLM Analysis ──> Report (MD + JSON)
              Multi-Product Comparison <──┘
```

## Quick Start

**Prerequisites:** Python 3.11+ and an OpenAI-compatible LLM endpoint.

```bash
# 1. Clone and install
git clone https://github.com/<your-username>/sift.git
cd sift
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env with your LLM API key and optional source API keys

# 3. Run!
python -m src.cli analyze "Notion" "Obsidian"
```

## CLI Commands

```bash
# Analyze a single product
python -m src.cli analyze "Linear"

# Compare multiple products
python -m src.cli analyze "Figma" "Sketch" "Penpot"

# Use only specific data sources
python -m src.cli analyze "Slack" --source g2
python -m src.cli analyze "VS Code" --source github_issues --source hacker_news

# Enable debug logging for troubleshooting
python -m src.cli analyze "Notion" --verbose

# Just scrape (no analysis)
python -m src.cli scrape "Notion" --source g2 --source app_store
```

## Configuration

Edit `config.yaml` to tune the pipeline:

| Section | Key Options |
|---------|-------------|
| `sources` | `default_sources`, `disabled_sources` |
| `reddit` | `subreddits`, `max_posts`, `max_comments_per_post` |
| `g2` | `request_delay`, `max_pages`, `user_agent_rotation` |
| `app_store` / `play_store` | product-to-app/package mappings, locale, item limits |
| `youtube` | `video_ids`, `max_comments_per_video` |
| `github_issues` | product-to-repo mappings, item limits |
| `support_forums` / `changelogs` | URL templates or product URL mappings |
| `discord_exports` / `linkedin_comments` | public/export JSON paths or URLs |
| `clustering` | `embedding_model`, `umap_n_neighbors`, `hdbscan_min_cluster_size` |
| `llm` | `model`, `temperature`, `max_tokens` |
| `logging` | `level` (`INFO` or `DEBUG`), `format` |

LLM endpoint and API keys are set via `.env`:

```
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
YOUTUBE_API_KEY=optional-youtube-key
GITHUB_TOKEN=optional-github-token
```

Any OpenAI-compatible API works — OpenAI, Anthropic (via proxy), Ollama, OpenCode, etc.

## Data Sources

| Source | Method | Requirements |
|--------|--------|-------------|
| **G2** | Web scraping (BeautifulSoup) | None — includes User-Agent rotation and polite request delays |
| **App Store** | Apple customer reviews RSS | Product app IDs in `config.yaml` |
| **Play Store** | Public app details/reviews page | Product package names in `config.yaml` |
| **YouTube comments** | YouTube Data API | `YOUTUBE_API_KEY` and product video IDs |
| **Hacker News** | Algolia HN Search API | None |
| **GitHub issues** | GitHub Search API | Product repos; optional `GITHUB_TOKEN` |
| **Product Hunt comments** | Public product pages | Optional product slugs |
| **Support forums** | Configured public search URLs | Forum URL templates |
| **Changelogs** | Configured public changelog URLs | Product URL mappings |
| **Discord exports** | Public/exported JSON | JSON file paths or URLs |
| **LinkedIn comments** | Public/exported JSON | JSON file paths or URLs |
| **Reddit** | PRAW (official API) | Currently disabled in `sources.disabled_sources` until API approval |

> To reactivate Reddit later, remove `reddit` from `sources.disabled_sources` and add it to `sources.default_sources` if you want it in default runs.
>
> **Privacy:** Usernames and PII are stripped at ingestion. Only the review text and a clickable source link are retained.

## Output

Reports are saved to `output/` in two formats:

- **Markdown** — human-readable with severity badges, representative quotes, and comparison tables
- **JSON** — machine-readable structured data for dashboards or downstream tools

Each report includes:
- Overall product insights (LLM-generated)
- Top pain points ranked by severity
- Per-cluster summaries with representative user quotes
- For multi-product runs: shared vs. unique pain points + competitive insights

## Architecture

```
src/
├── scrapers/          # Source adapters for public feedback channels
├── pipeline/          # Embeddings, clustering, LLM analysis, comparison, rate limiting, deduplication
├── models/            # Data classes (FeedbackItem, ClusterResult, ProductReport)
├── config.py          # YAML + env var configuration loader
└── cli.py             # Click CLI (analyze, scrape commands)
tests/                 # 34 tests covering all modules
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Roadmap

- [ ] Reactivate Reddit source after API approval
- [ ] Web app with dashboard UI
- [ ] Continuous monitoring mode (track sentiment over time)
- [ ] Additional review sites (Trustpilot, Capterra)
- [ ] Slack/email alerting for new complaint spikes

## License

MIT
