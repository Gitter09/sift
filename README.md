# Sift

> Scrape user feedback from Reddit and G2, cluster complaints with ML, and generate AI-powered product insights — all from your terminal.

## What It Does

- **Scrapes** Reddit and G2 for real user feedback about any product
- **Clusters** complaints and pain points using sentence embeddings + UMAP + HDBSCAN
- **Analyzes** each cluster with an LLM to name themes, summarize issues, and rate severity
- **Compares** multiple products to surface shared vs. unique pain points

## How It Works

```
Reddit (PRAW API) ──┐
                     ├──> Feedback Items ──> Sentence Embeddings ──> UMAP + HDBSCAN
G2 (Web Scraping) ──┘                             (all-MiniLM-L12-v2)

                            ┌── Clustered Themes ──> LLM Analysis ──> Report (MD + JSON)
Multi-Product Comparison <──┘
```

## Quick Start

**Prerequisites:** Python 3.11+, Reddit API credentials, an OpenAI-compatible LLM endpoint.

```bash
# 1. Clone and install
git clone https://github.com/<your-username>/sift.git
cd sift
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env with your Reddit client ID/secret and LLM API key

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
python -m src.cli analyze "Notion" --source reddit
python -m src.cli analyze "Slack" --source g2

# Just scrape (no analysis)
python -m src.cli scrape "Notion" --source reddit --source g2
```

## Configuration

Edit `config.yaml` to tune the pipeline:

| Section | Key Options |
|---------|-------------|
| `reddit` | `subreddits`, `max_posts`, `max_comments_per_post` |
| `g2` | `request_delay`, `max_pages`, `user_agent_rotation` |
| `clustering` | `embedding_model`, `umap_n_neighbors`, `hdbscan_min_cluster_size` |
| `llm` | `model`, `temperature`, `max_tokens` |

LLM endpoint and API keys are set via `.env`:

```
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Any OpenAI-compatible API works — OpenAI, Anthropic (via proxy), Ollama, OpenCode, etc.

## Data Sources

| Source | Method | Requirements |
|--------|--------|-------------|
| **Reddit** | PRAW (official API) | Free Reddit API credentials ([create here](https://www.reddit.com/prefs/apps)) |
| **G2** | Web scraping (BeautifulSoup) | None — includes User-Agent rotation and polite request delays |

> Twitter/X support planned. Modular scraper design makes adding new sources straightforward.

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
├── scrapers/          # Reddit (PRAW) and G2 (BeautifulSoup) scrapers
├── pipeline/          # Embeddings, clustering, LLM analysis, comparison
├── models/            # Data classes (FeedbackItem, ClusterResult, ProductReport)
├── config.py          # YAML + env var configuration loader
└── cli.py             # Click CLI (analyze, scrape commands)
tests/                 # 18 tests covering all modules
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Roadmap

- [ ] Twitter/X data source
- [ ] Web app with dashboard UI
- [ ] Continuous monitoring mode (track sentiment over time)
- [ ] Additional review sites (Trustpilot, Product Hunt, Capterra)
- [ ] Slack/email alerting for new complaint spikes

## License

MIT
