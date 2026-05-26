# AGENTS.md

This file provides guidance for AI agents (including Factory Droid, Claude, GPT, and others) working on the Sift project.

## Project Overview

Sift is a product research tool that scrapes Reddit and G2 feedback, clusters complaints using ML (sentence embeddings + UMAP + HDBSCAN), and generates AI-powered product insights. It's a CLI tool with a modular architecture designed for eventual migration to a web app/dashboard.

## Quick Reference

- **Language:** Python 3.11+
- **Framework:** Click (CLI), PRAW (Reddit), BeautifulSoup (G2 scraping), sentence-transformers (embeddings)
- **Package name:** `sift`
- **CLI entry point:** `sift` (runs `src.cli:main`)
- **Test runner:** `python -m pytest tests/ -v`
- **Config:** `config.yaml` + `.env` (gitignored — contains API keys)

## Key Conventions

1. All tool references must use **"Sift"** — never "copilot", "product-copilot", or "Product Research Copilot"
2. New scrapers must implement `BaseScraper` abstract class with `scrape(product_name) -> List[FeedbackItem]` and `source_name` property
3. All config must flow through `src/config.py` — no hardcoded values. Use `config.yaml` for defaults, `.env` for secrets
4. LLM calls must use the OpenAI-compatible SDK with configurable `base_url` — no vendor lock-in
5. Rate limiting must be applied to all scrapers via `RateLimiter` or `PrawRateMonitor` from `src/pipeline/rate_limiter.py`
6. Report output must include both Markdown and JSON formats
7. All new features must have corresponding tests in `tests/`

## CRITICAL: ARCHITECTURE.md Maintenance

> **This is a strict, mandatory rule. Every AI agent working on this project MUST follow it.**

Whenever you make a **significant decision** that affects the project's architecture, data flow, error handling strategy, rate limiting approach, scraper design, pipeline behavior, or user-facing behavior, you MUST:

1. **Add a new numbered entry** to `ARCHITECTURE.md` using the format:
   ```
   ## Decision NNN: [Short Title]
   
   **Date:** YYYY-MM-DD
   **Context:** [What situation or problem triggered this decision]
   **Decision:** [What you decided to do]
   **Why:** [The reasoning behind the decision]
   **LinkedIn Angle:** [A one-sentence hook that can be repurposed into a LinkedIn post]
   ```

2. The "LinkedIn Angle" field is **not optional**. It must be present for every decision. This is how the project owner repurposes technical decisions into content.

3. Numbering must be sequential (check the latest entry in ARCHITECTURE.md and increment by 1).

4. "Significant" means: anything that would be interesting to explain to another developer, or that represents a non-obvious choice. This includes but is not limited to:
   - Choosing a library, model, or algorithm
   - Changing rate limiting or error handling behavior
   - Adding a new data source or pipeline step
   - Renaming or rebranding
   - Security-related decisions
   - Decisions about what NOT to do (e.g., "we decided NOT to use X because Y")

**Do NOT skip this step.** If you're unsure whether a decision is significant enough to document, document it anyway. Over-documentation is preferred over under-documentation.

## File Structure

```
src/
  scrapers/          # Reddit (PRAW) and G2 (BeautifulSoup) scrapers
  pipeline/          # Embeddings, clustering, LLM analysis, comparison, rate limiting
  models/            # Data classes (FeedbackItem, ClusterResult, ProductReport)
  config.py          # YAML + env var configuration loader
  cli.py             # Click CLI (analyze, scrape commands)
tests/               # 18+ tests covering all modules
output/              # Generated reports (gitignored)
```

## Rate Limiting Reference

- **Reddit:** 60 req/min (OAuth). Sift targets 50 req/min. PRAW `ratelimit_seconds=300`.
- **G2:** No official API. Cloudflare + Akamai protection. Sift targets 12 req/min with exponential backoff + jitter.
- Both use `src/pipeline/rate_limiter.py` — `RateLimiter` (token bucket) for HTTP scrapers, `PrawRateMonitor` for Reddit.

## Error Handling Strategy

- Scrapers: exponential backoff with jitter on rate limit responses (429/403), max 3 retries
- Reddit: PRAW auto-handles rate limit headers; we set `ratelimit_seconds=300` for resilience
- Pipeline: if feedback count < 3, skip analysis (too few items to cluster meaningfully)
- LLM: structured JSON prompts with fallback parsing; if LLM call fails, use cluster labels as fallback
- Reports: always generate both Markdown and JSON; save to `output/` directory

## Roadmap

- [ ] Twitter/X data source (scrapers/twitter.py)
- [ ] Web app with dashboard UI (FastAPI wrapping existing modules)
- [ ] Continuous monitoring mode (scheduled runs, track sentiment over time)
- [ ] Additional review sites (Trustpilot, Product Hunt, Capterra)
- [ ] Slack/email alerting for new complaint spikes
