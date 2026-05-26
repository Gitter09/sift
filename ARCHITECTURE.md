# Sift Architecture Decisions

This document chronicles every significant architectural decision made during the development of Sift. It serves as both a technical reference and a content source for repurposing into LinkedIn posts, blog articles, and other content.

---

## Decision 001: Project Pivot — From General Web Crawler to Product Research Copilot

**Date:** 2025-05-25
**Context:** Originally planned to build a general web crawler capable of bypassing bot-protected sites like LinkedIn (using proxy rotation, CAPTCHA solving, anti-detect browsers like Camoufox).
**Decision:** Pivoted to a focused Product Research Copilot that scrapes Reddit/G2 feedback, clusters complaints, and generates insights.
**Why:** LinkedIn-level bot protection requires residential proxies ($1-15/GB), ongoing maintenance against evolving detection, and CAPTCHA solving services. A product research tool targets platforms with official APIs (Reddit) or mild protection (G2), making it 10x more feasible for someone relying on agentic AI workflows.
**LinkedIn Angle:** "Why I pivoted from building a LinkedIn scraper to a product insight tool — and why starting with accessible data sources is the smartest move for solo builders."

---

## Decision 002: Modular Scraper Architecture with Abstract Base Class

**Date:** 2025-05-25
**Context:** Need to support multiple data sources (Reddit, G2, and future: Twitter, Trustpilot, etc.)
**Decision:** Created `BaseScraper` abstract class with `scrape(product_name) -> List[FeedbackItem]` interface. Each source is a subclass. `ScraperFactory` returns the correct scraper by source name.
**Why:** Adding a new data source = just implement a new subclass. No changes to pipeline or CLI. This pattern also makes it easy to mock scrapers in tests.
**LinkedIn Angle:** "The scraper pattern that lets me add Twitter support in 30 minutes — why abstract base classes are your best friend in multi-source tools."

---

## Decision 003: Embedding Model Selection — all-MiniLM-L12-v2

**Date:** 2025-05-25
**Context:** Need to convert user feedback text into vector representations for clustering. Balance between quality, speed, and size.
**Decision:** Chose `all-MiniLM-L12-v2` (133M parameters) over `all-MiniLM-L6-v2` (80M).
**Why:** L12 has 12 transformer layers vs L6's 6 layers, giving better semantic understanding of complaint text. The size difference (133M vs 80M) is negligible on modern hardware. For clustering short feedback texts where nuance matters ("slow loading" vs "slow sync" are different complaints), the extra layers are worth it.
**LinkedIn Angle:** "Why I chose a bigger embedding model for clustering user complaints — when 6 layers aren't enough to tell 'slow' from 'broken'."

---

## Decision 004: Clustering Pipeline — UMAP + HDBSCAN

**Date:** 2025-05-25
**Context:** Need to auto-cluster user feedback into complaint themes without pre-specifying the number of clusters.
**Decision:** UMAP for dimensionality reduction (from 384-dim embeddings to 5-dim) → HDBSCAN for density-based clustering.
**Why:** K-means requires specifying k upfront and doesn't handle noise. HDBSCAN auto-detects cluster count, labels noise points as -1, and handles variable cluster sizes. UMAP preserves local structure better than PCA for text embeddings. The combo is the gold standard for semantic text clustering.
**LinkedIn Angle:** "Why K-means is the wrong choice for clustering user complaints — and why HDBSCAN + UMAP is the gold standard for finding themes you didn't know existed."

---

## Decision 005: LLM-Driven Cluster Analysis with OpenAI-Compatible API

**Date:** 2025-05-25
**Context:** Need to name clusters, summarize pain points, and rate severity. These are tasks embeddings/clustering can't do alone.
**Decision:** Use OpenAI-compatible API (configurable base_url) for cluster naming and insight generation. Each cluster gets a structured JSON response with label, summary, and severity.
**Why:** OpenAI-compatible format means the tool works with any provider — OpenAI, Claude (via proxy), Ollama (local), or any third-party endpoint. No vendor lock-in. The structured JSON prompts ensure consistent, parseable output.
**LinkedIn Angle:** "How I avoid LLM vendor lock-in while still getting great cluster analysis — the OpenAI-compatible API pattern that works with any provider."

---

## Decision 006: Multi-Product Comparison Architecture

**Date:** 2025-05-25
**Context:** Users want to compare multiple products to find shared vs. unique pain points.
**Decision:** Each product goes through its own scrape → embed → cluster → analyze pipeline independently. Then a separate `Comparator` takes all `ProductReport` objects and asks the LLM to identify shared vs. unique pain points.
**Why:** Independent pipelines avoid cross-contamination of clusters. The comparison step uses already-summarized cluster data (not raw text), keeping LLM costs low. Fallback comparison (cluster label intersection) works even if the LLM call fails.
**LinkedIn Angle:** "The two-step architecture that makes multi-product comparison reliable — cluster independently, compare on summaries."

---

## Decision 007: CLI-First, Web App Later

**Date:** 2025-05-25
**Context:** Need to decide the initial interface. User has no coding background and uses agentic AI workflows.
**Decision:** Start with a CLI tool (Click framework). Architecture is modular so CLI → web app migration is just adding a FastAPI layer on top.
**Why:** CLI is the simplest thing that works. `src/cli.py` → becomes FastAPI router. `models/` → become Pydantic API models. `pipeline/` → background tasks. Zero refactoring needed.
**LinkedIn Angle:** "Why I'm building a CLI tool before a web dashboard — and how modular architecture means zero refactoring when I add the UI layer."

---

## Decision 008: Anti-Bot Safeguards for G2 Scraping

**Date:** 2025-05-25
**Context:** G2 uses Cloudflare (8/10 bypass difficulty) + Akamai (9/10 bypass difficulty). ScrapeOps rates it 9/10 overall. No official API.
**Decision:** Implemented three layers of protection:
1. User-Agent rotation (5 realistic browser UA strings, randomly selected per request)
2. Configurable request delay (default 2.5s between requests)
3. Exponential backoff with jitter on 429/403 responses
**Why:** Raw HTTP requests with fixed delays and a single User-Agent will get blocked within 20-30 requests. UA rotation makes each request look like a different browser. Jitter prevents predictable patterns that Cloudflare's behavioral analysis detects. Exponential backoff ensures we don't hammer the server when limits are hit.
**LinkedIn Angle:** "3 layers of anti-bot safeguards that let me scrape a Cloudflare-protected site without paying for a proxy service — and why jitter is the secret ingredient."

---

## Decision 009: Reddit API Rate Limiting Strategy

**Date:** 2025-05-25
**Context:** Reddit API allows 100 QPM / 1000 per 10 min for OAuth script apps. PRAW auto-handles rate limit headers but has a default `ratelimit_seconds=5` which aborts on longer waits.
**Decision:** Three-part strategy:
1. Set PRAW's `ratelimit_seconds=300` so it auto-waits up to 5 minutes on rate limit errors instead of crashing
2. Target 50 req/min (leaving generous headroom for PRAW's internal calls)
3. Add `PrawRateMonitor` that tracks request count and enforces pace — sleeps proportionally if rate exceeds target
**Why:** PRAW's default 5s limit causes crashes on long scraping runs. Raising to 300s makes the scraper resilient. Targeting 50/min instead of 100/min accounts for PRAW's internal pagination requests that you don't explicitly see. The monitor logs rate info every 10 requests so you can see pacing in action.
**LinkedIn Angle:** "How I made my Reddit scraper crash-proof — the 3-layer rate limiting strategy that PRAW doesn't tell you about."

---

## Decision 010: Exponential Backoff with Jitter for G2

**Date:** 2025-05-25
**Context:** G2's Cloudflare/Akamai protection returns 429 (rate limited) and 403 (forbidden/bot detected) responses. Simple retry with fixed delay doesn't work.
**Decision:** Implemented `RateLimiter` class with:
- Token-bucket rate control (max 12 req/min for G2)
- Exponential backoff: delay = min(2^attempt, 60s) * random(0.8, 1.2)
- Max 3 retries before giving up
- Jitter multiplier on base request delay to prevent predictable patterns
**Why:** Fixed delays create a predictable pattern that behavioral analysis can detect. Exponential backoff progressively slows down on repeated blocks. Jitter on both the base delay AND backoff makes each request timing unique. The math: attempt 1 = ~2s, attempt 2 = ~4s, attempt 3 = ~8s, all with ±20% random variance.
**LinkedIn Angle:** "The math behind anti-bot backoff: why 2^n * random(0.8,1.2) is the formula that keeps my scraper alive on Cloudflare-protected sites."

---

## Decision 011: .env Security — Gitignore Instead of Editing

**Date:** 2025-05-25
**Context:** .env.example contained real API keys. Need to prevent them from being pushed to GitHub.
**Decision:** Added both `.env` and `.env.example` to `.gitignore` instead of editing the file to remove keys.
**Why:** User preferred this approach so they don't have to re-enter API keys. The .env.example stays local with real values, gitignored so it never reaches GitHub. New users will need to create their own .env manually — this is documented in README.
**LinkedIn Angle:** "Why I gitignore .env.example instead of cleaning it — and the security trade-off most developers don't think about."

---

## Decision 012: Tool Renaming — product-copilot to Sift

**Date:** 2025-05-25
**Context:** The project was initially called "Product Research Copilot" with CLI entry point `copilot`.
**Decision:** Renamed to "Sift" across all references — package name, CLI entry point, config headers, user-agent string, docstrings, README.
**Why:** "Sift" is short, memorable, and evocative of the core action (sifting through feedback for insights). "Copilot" is overused and generic. Deep audit found 13 references across 6 files, all replaced with zero remaining "copilot" traces.
**LinkedIn Angle:** "Why I renamed my tool from 'Product Copilot' to 'Sift' — and the deep codebase audit that found 13 references I had to replace."

---

## Decision 013: PII-Free Ingestion, Hash-Based Deduplication, and Structured Logging

**Date:** 2026-05-26
**Context:** The tool was storing usernames (PII) in FeedbackItem.author, used ad-hoc text-based deduplication per scraper, and relied on print() statements everywhere with no configurable log levels.

**Decision:**
1. **Anonymous reviews by default** — removed the `author` field from `FeedbackItem` entirely. Usernames are PII and add no analytical value. Each review retains a clickable `url` to the original source.
2. **Deterministic hash IDs** — every `FeedbackItem` now auto-generates a 16-char SHA-256 hex ID from `source:url` (or `source:text` as fallback). A new `DedupFilter` class in `src/pipeline/dedup.py` tracks seen IDs across scrapers, making deduplication a pipeline concern, not a scraper concern.
3. **Structured logging** — replaced all `print()` calls across 12 files with Python's `logging` module. Added `LoggingConfig` to `Settings` (configurable via `config.yaml`), `setup_logging()` for one-time initialization, and a `--verbose`/`-v` CLI flag. Human-facing progress messages use `click.echo()`, while diagnostics use `logger.info/debug/warning/error/exception`. Error messages are user-friendly (e.g., "Reddit rate limit hit on r/SaaS. Waiting 60s before trying next subreddit." instead of raw exception dumps).

**Why:** PII-free ingestion is a privacy best-practice and simplifies GDPR compliance. Hash-based IDs prevent duplicates across scrapers (e.g., if Reddit and G2 scrape the same content). Structured logging with levels means production runs stay quiet while `--verbose` enables on-demand debugging — critical for long-running scrape jobs.

**LinkedIn Angle:** "How I made my web scraper PII-free, deduplication-safe, and debuggable in 3 decisions — and why print() is the worst logging library."
