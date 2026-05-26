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


---

## Decision 019: Interactive CLI — Zero-Argument Entry Point with First-Run Setup

**Date:** 2026-05-26
**Context:** Running `sift` with no arguments showed a bare Click help page. New users had to learn subcommand syntax and manually create a `.env` file with API keys before the tool could do anything useful.
**Decision:** Running `sift` with no arguments now launches a rich-powered interactive CLI. On first run, a setup wizard prompts for API keys (LLM key required, others optional) and saves them to `.env`. Subsequent runs go straight to a numbered main menu (Analyze, Scrape, Settings, Exit). The existing `sift analyze` and `sift scrape` subcommands continue working unchanged for scripts and CI.
**Why:** A setup wizard eliminates the biggest onboarding friction — manually editing a `.env` file. The interactive menu makes Sift usable without memorizing CLI flags, which is critical for the target audience (non-developer product researchers). Extracting pipeline runners (`run_analyze`, `run_scrape`) from Click callbacks into standalone functions keeps the core logic reusable across both the CLI commands and the interactive menu without duplication.
**LinkedIn Angle:** "How I turned a CLI tool into something my non-technical friends can use — zero arguments, a setup wizard, and a numbered menu."

---

## Decision 020: Default Source Filtering and Quiet Normal-Mode Diagnostics

**Date:** 2026-05-26
**Context:** A default `sift analyze "Notion"` run displayed many configured source names, then skipped most of them because product-specific IDs, repos, video IDs, URLs, or export paths were missing. Scraper logs also interleaved with Rich progress output, and scrape-only commands imported the UMAP clustering stack before scraping.
**Decision:** Default runs now include only sources that are enabled and currently runnable from configuration. Always-runnable public sources remain available by default, while App Store, Play Store, YouTube, GitHub issues, support forums, changelogs, Discord exports, and LinkedIn exports join default runs only after their required config exists. Scraper diagnostics are quiet in normal mode and visible with `--verbose`; no-feedback runs print explicit setup guidance. The CLI also lazy-loads embedding, clustering, analysis, and comparison modules only after enough feedback exists for analysis.
**Why:** A default run should represent work Sift can actually attempt, not a list of theoretical future integrations. Filtering unconfigured sources reduces misleading output, quiet diagnostics keep progress UI readable, no-feedback guidance gives the user a next action, and lazy ML imports prevent scrape-only workflows from failing on unrelated UMAP/numba environment issues.
**LinkedIn Angle:** "The boring product lesson from a scraper CLI: default behavior should reflect what is actually runnable, not what your architecture theoretically supports."

---

## Decision 021: Runtime-Safe Browser and LLM Fallbacks

**Date:** 2026-05-26
**Context:** Product Hunt could trigger Playwright's "Sync API inside the asyncio loop" error during fallback fetching. Post-clustering analysis also crashed before the LLM call because prompt templates used literal JSON braces with `str.format()`, and expected LLM failures surfaced full tracebacks even though Sift is designed to continue with fallback labels.
**Decision:** Browser fallback now detects a running asyncio loop and performs sync Playwright work in a helper thread with an isolated browser instance. Analyzer and comparator prompts escape literal JSON braces, tolerate missing or invalid LLM configuration, skip LLM calls when unavailable, and use deterministic fallback summaries without traceback logging for expected API failures.
**Why:** Scrapers expose a synchronous interface, so moving only the browser fallback into a thread preserves the existing scraper contract while avoiding Playwright's sync API limitation. Escaped prompt schemas make the analysis stage reachable, and quiet deterministic LLM fallbacks keep successful scrape and clustering runs usable even when credentials, network, or model providers fail.
**LinkedIn Angle:** "A scraper can survive two fragile dependencies: isolate browser fallbacks from event loops, and make AI analysis optional instead of pipeline-breaking."

---

## Decision 022: Monochromatic B&W CLI Aesthetic with Arrow-Key Menu Navigation

**Date:** 2026-05-26
**Context:** The Sift main menu used a solid cyan color scheme throughout — logo, panel borders, prompt labels, menu numbers — giving a "hacker terminal" look that felt inconsistent with a professional product research tool. The menu also required the user to type a number and press Enter rather than using keyboard navigation, which felt clunky for an interactive UI.
**Decision:** Replaced all decorative cyan/blue colors with a white/dim monochromatic hierarchy. The SIFT logo now renders with a top-to-bottom brightness gradient (`bold bright_white` → `bold white` → `white`) to add depth without color. Panel borders and prompt labels use `white` and `bold`. Implemented real arrow-key navigation for the main menu using raw terminal I/O (`termios`/`tty`/`select` from stdlib) — `↑`/`↓` moves a `▶` indicator, `Enter` confirms, `q` exits. Functional severity indicators (red/yellow/green) were deliberately preserved since they carry semantic meaning.
**Why:** B&W aesthetics signal confidence — color is often used to compensate for weak visual structure, whereas a well-structured monochrome UI looks intentional and polished. The gradient on the logo gives perceived depth without brightness inconsistency. Arrow-key navigation is the standard expectation for any modern interactive CLI (fzf, lazygit, k9s all do this); a numbered prompt forces the user to read, remember, type, and press Enter when a single keypress is more natural. The raw-terminal approach uses only stdlib (`termios`, `tty`, `select`) — zero new dependencies — and handles the escape-sequence timing edge case with a 50ms `select()` drain to correctly distinguish bare Escape from arrow-key sequences.
**LinkedIn Angle:** "Why I stripped all color from my CLI tool's UI — and how a top-to-bottom white gradient replaced it without losing any visual depth."

---

## Decision 023: Provider-Tolerant LLM Prompting and JSON Parsing

**Date:** 2026-05-26
**Context:** Sift uses OpenAI-compatible chat endpoints, but real deployments may route through providers such as OpenCode Go with DeepSeek models that do not always return pristine JSON even when prompted. A single non-JSON prefix, markdown fence, or empty response caused product-level insights and comparisons to fall back unnecessarily.
**Decision:** Analyzer and comparator prompts now use explicit system/user message roles, evidence-bound task sections, output schemas, and rules that forbid invented facts or markdown. LLM responses are parsed through a shared tolerant JSON extractor that strips code fences, extracts the first balanced JSON object from wrapped prose, validates object shape, logs sanitized debug previews on parse failures, and makes one schema-focused repair attempt before falling back.
**Why:** Prompt wording alone is not a reliability boundary when multiple OpenAI-compatible providers sit behind the same client interface. Combining clearer task framing with provider-tolerant parsing preserves Sift's current report schema while making analysis resilient to the common formatting quirks of non-OpenAI endpoints.
**LinkedIn Angle:** "The real lesson from using 'OpenAI-compatible' APIs: compatibility gets you a response, but robust parsing turns it into a product feature."

---

## Decision 024: Writable Numba Cache for UMAP Imports

**Date:** 2026-05-26
**Context:** UMAP imports numba-compiled functions with caching enabled. On framework Python installs where global `site-packages` is not writable, importing `umap` can fail before Sift reaches clustering with `RuntimeError: cannot cache function 'rdist': no locator available`.
**Decision:** Added a small clustering bootstrap helper that sets `NUMBA_CACHE_DIR` to a writable temp directory (`sift-numba-cache`) before importing UMAP, while preserving any user-provided `NUMBA_CACHE_DIR`.
**Why:** The clustering stack should not depend on write access to global Python package directories. A temp-backed default keeps CLI and test runs portable across locked-down global installs, virtualenvs, and CI while still allowing advanced users to choose their own cache location.
**LinkedIn Angle:** "A tiny environment default saved my ML pipeline from global Python permissions: make caches explicit before libraries guess wrong."

---

## Decision 025: HN Recency Filter via `search_by_date`

**Date:** 2026-05-26
**Context:** Hacker News searches used the Algolia `search` endpoint, which ranks by relevance (upvotes × recency). For product research, a highly upvoted 3-year-old thread dominated results over recent discussions, making Sift's HN output historically skewed rather than current.
**Decision:** Switched both story and comment searches from the `search` endpoint to `search_by_date`, adding a `numericFilters=created_at_i>{cutoff}` parameter. Default window is 180 days, configurable via `hacker_news.recency_days` in `config.yaml`.
**Why:** Product feedback is time-sensitive — a complaint about a bug fixed two years ago is noise, not signal. The `search_by_date` endpoint returns results sorted by creation time, and the `numericFilters` unix timestamp cutoff excludes anything older than the configured window without requiring a post-fetch filter pass.
**LinkedIn Angle:** "One Algolia endpoint swap turned our HN scraper from a history lesson into actual recent product feedback."

---

## Decision 026: G2 Paid-Proxy Warning and Proxy Pass-Through

**Date:** 2026-05-26
**Context:** G2 reviews are behind Cloudflare and Akamai bot protection. Even with curl_cffi TLS fingerprint impersonation and a Playwright fallback, G2 consistently returned 403s in practice. Users who included G2 as a source got 0 results with no explanation.
**Decision:** When G2 is selected without a proxy configured, Sift now shows a Rich Panel warning explaining the limitation and listing compatible paid proxy services (ScraperAPI, ZenRows, BrightData, Oxylabs) with exact config instructions for both `config.yaml` (`g2.proxy_url`) and `.env` (`G2_PROXY_URL`). The scraper still runs — occasional Cloudflare misses do occur — but the user understands the expected outcome. Proxy URLs are passed to curl_cffi via `proxies={"https": url, "http": url}`.
**Why:** Silently returning 0 results from a source the user explicitly selected is misleading. The warning turns a confusing failure into an actionable diagnosis: "add a proxy to fix this." Keeping the scraper running preserves value for users who have proxies and for the rare successful bypass.
**LinkedIn Angle:** "Don't silently fail on Cloudflare — tell the user exactly what's blocked and exactly how to unblock it."

---

## Decision 027: Product Hunt GraphQL API v2 as Primary Path

**Date:** 2026-05-26
**Context:** Product Hunt's HTML structure is heavily JavaScript-rendered and frequently returns 403s to headless browsers. The scraper was getting 0 results in most runs. Product Hunt offers an official GraphQL API v2 with free developer tokens.
**Decision:** Rewrote `ProductHuntScraper` to use the official PH GraphQL API v2 (`https://api.producthunt.com/v2/api/graphql`) as the primary path. The `PRODUCT_HUNT_TOKEN` env var (or `product_hunt.developer_token` in config) enables the API path, which fetches posts + taglines + comments via a single GraphQL query. When no token is configured, the scraper falls back to the original HTML scraping path.
**Why:** Using an official API is more reliable, faster, and respects the platform's intended access model. The free developer token has generous limits for research workloads. Keeping HTML as a fallback means the scraper still attempts something when no token is set rather than returning 0 results immediately.
**LinkedIn Angle:** "When a site keeps 403-ing your scraper, check if they have an official API — Product Hunt's is free and works perfectly."

---

## Decision 028: GitHub Issues Auto-Discovery Without Repo Config

**Date:** 2026-05-26
**Context:** `GitHubIssuesScraper` only fetched issues from repos explicitly listed in `github_issues.repos` config. For most products, users didn't know which repos to list, so the scraper was a no-op by default despite GitHub having an open search API.
**Decision:** `GitHubIssuesScraper.scrape()` now checks `config.repos` first; if no repos are configured for the product, it falls back to `_search_all_github()`, which queries the GitHub search API (`/search/issues?q="product"+in:title&sort=created&order=desc`) across all public repositories. Explicit repo lists still take priority and use the per-repo fetch path.
**Why:** GitHub Issues contains high-signal technical complaints and feature requests. Making it zero-config — search all of GitHub when no repos are specified — means every product gets GitHub coverage out of the box without any setup. The search API is free and unauthenticated at 10 req/min (60/min with a token).
**LinkedIn Angle:** "Stop requiring config before your tool does anything useful — GitHub's search API makes issues discovery zero-config."

---

## Decision 029: Stack Overflow Scraper via Stack Exchange Open API

**Date:** 2026-05-26
**Context:** Stack Overflow is a high-signal source of product pain points (questions about bugs, missing features, confusing APIs). The Stack Exchange API v2.3 is public and requires no key for basic usage, making it a natural zero-config source.
**Decision:** Added `StackOverflowScraper` using the `/search/excerpts` Stack Exchange API endpoint. Returns question titles and excerpts sorted by relevance. The API allows 300 requests/day unauthenticated; registering a free app at stackapps.com raises this to 10,000/day (`STACK_OVERFLOW_KEY` env var / `stack_overflow.api_key` config). Added to `default_sources`.
**Why:** Stack Overflow questions represent real developer friction that product teams need to know about. The excerpts endpoint returns enough context (title + body snippet) to feed the clustering pipeline without needing full question fetches. Zero-config default with an optional key for higher limits matches Sift's design principle of working out of the box while rewarding configuration.
**LinkedIn Angle:** "Stack Overflow has a free API that needs no signup — and it's one of the best sources of honest product pain points."

---

## Decision 030: Dev.to Scraper via Internal Search Endpoint

**Date:** 2026-05-26
**Context:** Dev.to articles frequently contain product reviews, tutorials, and criticism that reflect developer sentiment. Dev.to has no official public API, but its internal search endpoint (`/search/feed_content`) is used by its own frontend and returns structured JSON without authentication.
**Decision:** Added `DevToScraper` using `https://dev.to/search/feed_content?q={query}&content_type=article`. Returns article titles and body previews. No API key or registration required. Added to `default_sources`.
**Why:** Dev.to content skews toward developer products and tools — exactly the audience Sift's target users care about. The internal endpoint returns clean structured JSON and has no documented rate limits (politely throttled to 20 req/min). Using an undocumented internal endpoint carries the risk of breakage, but it's the same data the public site serves and is a reasonable pragmatic choice for a research tool.
**LinkedIn Angle:** "Dev.to has no public API, but its frontend does — and the internal search endpoint returns exactly the structured data you need."

---

## Decision 031: Pipeline Progress Bar Per-Cluster Granularity

**Date:** 2026-05-26
**Context:** `PipelineProgress` tracked 4 fixed stages (embed, cluster, analyze, insights). For a product with 7 clusters, the bar jumped from 50% to 75% only after all 7 LLM calls completed — sometimes a 2–3 minute freeze with no visual feedback that anything was happening.
**Decision:** Added `set_total()` to `PipelineProgress` so the total can be updated after clustering reveals the cluster count. `cli.py:run_analyze` starts with `total_stages=2` (embed + cluster), then calls `pipeline.set_total(2 + n + 1)` once clustering completes, and advances once per cluster in a per-cluster loop with description "Analysing — {product} ({i}/{n})". The final insights call advances the last unit.
**Why:** The progress bar is the user's only signal that a long-running operation is alive. A 3-minute freeze at 50% looks like a hang. Per-cluster granularity makes the bar move once per LLM call (~5–15 seconds) and shows which cluster number is being processed, giving the user a live ETA feel even without an actual time estimate.
**LinkedIn Angle:** "A progress bar that freezes for 3 minutes at 50% is worse than no progress bar — make it tick once per unit of real work."

---

## Decision 032: G2 Excluded from Default Sources Without a Proxy

**Date:** 2026-05-26
**Context:** G2 was always included in `default_sources()` because `is_source_configured("g2")` returned `True` unconditionally. Users who never configured a G2 proxy would see the large yellow proxy-warning panel every time they ran a multi-product analysis — once per product — even if they had not intentionally selected G2.
**Decision:** Changed `is_source_configured("g2", settings)` to return `bool(settings.g2.proxy_url)`. G2 now only appears in default sources when a proxy is configured. Also added a module-level `_g2_proxy_warning_shown` flag in `factory.py` so the proxy warning is printed at most once per process, regardless of how many products are being analyzed.
**Why:** A source that reliably returns 0 results (because Cloudflare blocks every request without a proxy) should not be in the default active set. It wastes time, prints a confusing warning, and trains users to ignore warnings. The warning deduplication prevents repetitive noise when multiple products are analyzed in a single run.
**LinkedIn Angle:** "If a scraper needs paid infrastructure to work, it shouldn't silently appear in your default sources — gate it on configuration."

---

## Decision 033: Progress Bars Persist and Show M-of-N Counts

**Date:** 2026-05-26
**Context:** Both `ScrapeProgress` and `PipelineProgress` used `transient=True`, which erases the bar from the terminal when the context block exits. Users saw the bar flash briefly and disappear — it was purely decorative because no trace remained after completion. The percentage also jumped in large steps rather than advancing smoothly.
**Decision:** Removed `transient=True` from both progress classes so bars stay visible after completion. Added `MofNCompleteColumn` between the bar and the percentage so the output reads e.g. "7/16 • 44% • 0:08" — showing tasks completed rather than just a fraction of the filled rectangle.
**Why:** A progress indicator that vanishes the moment work is done provides no information — it can't be read after the fact and doesn't let the user gauge how long a phase took. Persisting the bar turns it into a lightweight execution log: users can see that scraping took 16 tasks and the pipeline took 5 stages, which is genuinely useful context when something is slow or fails.
**LinkedIn Angle:** "A progress bar that disappears the moment it hits 100% is a spinner in disguise — persist it so users can actually read what just happened."
