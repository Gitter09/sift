---
name: qa-cli
description: >
  QA tests for the copilot CLI app. Tests the scrape and analyze pipelines
  with multiple personas, error handling, and boundary conditions.
  Uses tuistory for interactive TUI testing.
---

# QA: copilot CLI

Tests the Product Research Copilot CLI tool (`copilot`).

## Testing Target

This is a CLI-only app. Testing always runs locally:

1. Build: `pip install -e '.[dev]'`
2. The `copilot` command must be available on PATH after install
3. Test by running CLI commands directly or via tuistory for TUI interaction

## App Configuration

- CLI framework: Click (commands: `analyze`, `scrape`)
- Entry point: `src/cli.py`
- Python: 3.11+
- Config file: `config.yaml` (optional, defaults are built-in)
- Environment variables from `.env` or CI secrets

## Pre-flight Checks

Before any test flows, verify:

```
pip install -e '.[dev]'    # Must succeed
copilot --help             # Must show help text
```

Check env vars (warn if missing, don't block):
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` — Reddit scraper needs these
- `LLM_API_KEY` — LLM analysis needs this
- `LLM_BASE_URL` — defaults to https://api.openai.com/v1 if not set

The Reddit scraper gracefully skips if creds are missing. The LLM analyzer will fail if the key is missing.

## Authentication in CI

No user authentication exists for this CLI. Required API keys come from GitHub Secrets:

- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — Reddit API
- `LLM_API_KEY`, `LLM_BASE_URL` — LLM API endpoint

These are injected as environment variables by the CI workflow. If any are missing, note it in the report but proceed with flows that don't need them.

## Test Flows

Use the `droid-control` skill for all tuistory interactions.

### Flow 1: analyze happy path

Tests the full pipeline: scrape → embed → cluster → LLM analyze → report generation.

1. Run: `copilot analyze "Notion" -s reddit`
2. Verify output contains: `[Scrape] Collecting reddit feedback for 'Notion'...`
3. Verify output contains: `[Pipeline] Embedding`
4. Verify output contains: `[Pipeline] Clustering`
5. Verify output contains: `[Pipeline] Analyzing`
6. Verify output contains: `[Done] Reports saved`
7. Verify output files exist: `output/notion_*.md` and `output/notion_*.json`

**Expected duration:** 30-90 seconds (depends on Reddit API + LLM latency)

**Success criteria:** Reports generated with insights, top_pain_points present.

### Flow 2: scrape happy path

Tests the raw scrape-only command (no analysis pipeline).

1. Run: `copilot scrape "Notion" -s reddit -o output`
2. Verify output contains: `[Scrape] Collecting reddit feedback`
3. Verify output contains: `[Scrape] Saved`
4. Verify file exists: `output/notion_raw.json`
5. Verify JSON is valid and contains `FeedbackItem` entries

**Expected duration:** 10-30 seconds

**Success criteria:** Raw JSON file generated with feedback items.

### Flow 3: missing Reddit API keys

Tests graceful handling when Reddit credentials are not set.

1. Unset `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (or run in a clean env without them)
2. Run: `copilot analyze "Notion"`
3. Verify output contains: `[Config] Reddit credentials not set, skipping Reddit scraper`
4. Verify G2 scraper still attempts to run
5. Verify tool does NOT crash with an unhandled exception

**Success criteria:** Graceful skip message, no crash, tool continues.

### Flow 4: invalid/missing product

Tests error handling for products that produce no results.

1. Run: `copilot analyze "xyznonexistentproduct2025"`
2. Verify output shows the tool runs without crashing
3. If `[Pipeline] Too few feedback items` appears, verify it exits cleanly
4. Verify no traceback or unhandled exception is printed

**Success criteria:** Tool handles no-results gracefully, no crash.

### Flow 5: too few results (boundary condition)

Tests the pipeline's handling when fewer than 3 feedback items are returned.

1. Run: `copilot analyze "gibberishproductxyz123"` (or a product likely to return <3 results)
2. Verify output contains: `[Pipeline] Too few feedback items` AND `skipping analysis`
3. Verify no reports are generated for that product

**Success criteria:** Pipeline correctly skips analysis when feedback < 3 items.

## Known Failure Modes

1. **Reddit API rate limiting.** PRAW may throttle or return errors under heavy use. If Reddit scraping fails with 429, wait 60s and retry.
2. **G2 HTML parsing fragility.** G2 periodically changes their review page HTML selectors. If G2 returns 0 reviews, check if the selectors in `src/scrapers/g2.py` still match.
3. **LLM API timeouts.** The api.freemodel.dev endpoint may lag or return errors. If LLM calls time out, report as BLOCKED with the API response.
4. **sentence-transformers first-run download.** The embedding model (`all-MiniLM-L12-v2`) downloads on first use (~80MB). If no network, the embed step fails.
5. **HDBSCAN requires ≥3 items.** The clusterer prints a warning and returns a single group for <3 items. This is expected behavior, not a failure.

## CI Mode Notes

In CI, the workflow injects `CI=true`. When running in CI:

- Do NOT use AskUser or wait for confirmation
- Do NOT pause for input
- Prefix CLI commands with `env -u CI` if the app detects CI and changes behavior
- Use session name `-s qa-test` with `--cols 110 --rows 36` for tuistory
- All output goes to `qa-results/` directory for artifact upload
