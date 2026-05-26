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
2. Target 80 req/min (leaving generous headroom for PRAW's internal calls)
3. Add `PrawRateMonitor` that tracks request count and enforces pace — sleeps proportionally if rate exceeds target
**Why:** PRAW's default 5s limit causes crashes on long scraping runs. Raising to 300s makes the scraper resilient. Targeting 80/min instead of 100/min accounts for PRAW's internal pagination requests that you don't explicitly see. The monitor logs rate info every 10 requests so you can see pacing in action.
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

---

## Decision 014: Config-Gated Source Portfolio While Reddit Approval Is Pending

**Date:** 2026-05-26
**Context:** Reddit API access requires manual approval, so the default pipeline needed to stop depending on Reddit while still preserving the scraper for reactivation later.
**Decision:** Added a `sources` config section with `default_sources` and `disabled_sources`, put `reddit` in `disabled_sources`, and expanded the source registry to include G2, App Store, Play Store, YouTube comments, Hacker News, GitHub issues, Product Hunt comments, public support forums, changelogs, public Discord exports, and LinkedIn comment exports. Sources that require product-specific IDs, repos, video IDs, forum URLs, or exported JSON now skip cleanly until configured.
**Why:** Muting Reddit through configuration keeps the existing PRAW implementation intact and makes reactivation a one-line config change. A broader source portfolio keeps Sift useful during approval wait time, while explicit per-source config avoids brittle scraping guesses or unauthorized collection from channels that need exports or API keys.
**LinkedIn Angle:** "What I did when an API approval blocked my roadmap: feature-flag the dependency, keep the interface stable, and widen the data portfolio instead of waiting."

---

## Decision 015: Rich-Powered Terminal UI Layer

**Date:** 2026-05-26
**Context:** The CLI used bare `click.echo()` and `print()` for all output — no progress bars, no formatted tables, no visual structure. Long-running pipeline steps (scraping, embedding, clustering, LLM analysis) gave zero feedback until completion.
**Decision:** Added `rich>=13.0` as a dependency and created a dedicated UI layer at `src/ui/display.py` that wraps all terminal output: Sift ASCII banner, config summary panels, `ScrapeProgress` and `PipelineProgress` context managers (spinner + bar + elapsed time), cluster summary tables (sorted by severity with color-coded badges), comparison panels, and in-terminal markdown report preview. The display layer has zero coupling to pipeline code — `cli.py` is the only consumer.
**Why:** Rich gives Droid/Hermes-level terminal polish without the async complexity of Textual or the infrastructure overhead of a React/Vite WebApp. A separate `src/ui/display.py` module keeps formatting concerns isolated from pipeline logic and makes it trivial to swap the presentation layer later (Textual TUI, WebApp API, or headless mode). Progress bars with elapsed time eliminate the "is it hung?" problem during long ML operations.
**LinkedIn Angle:** "How I made my CLI tool look like a $10K dashboard with one Python library — and why a separate UI layer is the cheat code for terminal polish."

---

## Decision 016: Release-Gated Python Package Distribution

**Date:** 2026-05-26
**Context:** Users should be able to install Sift without cloning the repository, while maintainers need confidence that published artifacts are tested and installable.
**Decision:** Added an explicit setuptools build backend and a GitHub Actions packaging workflow that runs the test suite on Python 3.11 and 3.12, builds both source distribution and wheel artifacts, validates metadata with Twine, smoke-tests the installed wheel through the `sift` CLI entry point, uploads package artifacts for every successful run, attaches packages to versioned GitHub Releases, and publishes to PyPI only from an explicit manual dispatch.
**Why:** Separating test, build, smoke-test, GitHub Release, and PyPI jobs keeps the release chain auditable. GitHub Release assets provide an immediate no-clone download path. PyPI publishing remains manual because the `sift` project name already exists on PyPI and will require either ownership of that project or a unique package rename before trusted publishing can succeed.
**LinkedIn Angle:** "The package release workflow I wish every CLI tool had: test it, build it, install the wheel, then publish only what actually runs."

---

## Decision 018: Rename Distribution Package to getsift

**Date:** 2026-05-26
**Context:** The `sift` distribution name is already occupied on PyPI, but the project should keep the user-facing CLI command and product name as Sift.
**Decision:** Renamed the Python distribution package from `sift` to `getsift` while preserving the console entry point as `sift`.
**Why:** Package names and command names are independent in Python packaging. Using `getsift` gives the project a publishable installer name (`pip install getsift`) without forcing users to run a different command or changing the product brand across the codebase.
**LinkedIn Angle:** "A practical packaging lesson: when the PyPI name is taken, rename the installer, not the product."


---

## Decision 017: Two-Tier Anti-Bot Strategy — curl_cffi + Playwright Fallback

**Date:** 2026-05-26
**Context:** G2 and Product Hunt scrapers were getting 403 blocked by Cloudflare/Akamai bot detection on every request. User-Agent rotation and jitter alone were insufficient — Cloudflare now checks TLS/JA3 fingerprints at the network layer, which the standard `requests` library can't spoof.

**Decision:** Implemented a two-tier anti-bot strategy:
1. **Tier 1 — `curl_cffi`**: Replaced `requests.Session` with `curl_cffi.requests.Session(impersonate="chrome124")` which impersonates Chrome's TLS fingerprint at the libcurl level. Same technique used by Crawlee's HTTP crawler. Handles 90%+ of Cloudflare-protected sites.
2. **Tier 2 — Playwright fallback**: On 403 responses, automatically launches a real Chromium browser via Playwright to fetch the page. The browser is launched once per scraper instance and reused across pages.

Both tiers are configurable via `use_playwright_fallback` in `config.yaml` per-source (G2, Product Hunt).

**Why:** `curl_cffi` is a lightweight drop-in replacement for `requests` — it adds ~5MB of shared libraries versus ~300MB for a full Chromium install. But some sites use advanced JS challenges that only a real browser can solve. The two-tier approach gives us the speed and simplicity of `curl_cffi` for most cases, with Playwright as a "nuclear option" when needed. This avoids the massive dependency footprint of tools like Browser-Use (AI agent, wrong paradigm), Firecrawl (full microservice platform, AGPL licensed), or Crawlee (Node.js, not Python) while using the same underlying anti-bot techniques.

**LinkedIn Angle:** "How I bypassed Cloudflare bot detection with a 5MB Python library instead of a 300MB browser — and why two-tier anti-bot strategy beats a monolithic scraping framework."
