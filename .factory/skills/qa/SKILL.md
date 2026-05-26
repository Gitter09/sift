---
name: qa
description: >
  Run QA tests for product-copilot (sift). Analyzes git diff to determine affected areas,
  runs configured test flows, and generates targeted tests using tuistory
  for CLI testing. Use when testing PRs, releases, or smoke testing.
---

# QA Orchestrator — product-copilot (sift)

**SCOPE: This skill performs manual/functional QA only — verifying that the application actually works by interacting with it as a real user would (TUI/CLI). Do NOT run or report on CI checks, linting, ESLint, typecheck, unit tests, or any static analysis. Those are handled by separate workflows.**

## Step 1: Load Configuration

Read `.factory/skills/qa/config.yaml` for environment URLs, credentials, personas, and app definitions.

## Step 2: Determine Target Environment

For this project, QA always runs locally against the installed CLI binary. No remote environments exist.

## Step 3: Analyze Git Diff

Run `git diff` to determine what changed. Map changed files to apps using the path_patterns in config.yaml.

Files that don't match ANY app's path_patterns (e.g., `.factory/skills/**`, `docs/**`, `.github/**`, config files) are NOT associated with any app. Do NOT run app test flows for them.

For each affected app:

- Run ONLY that app's flows from its sub-skill
- Generate ADDITIONAL targeted tests based on the specific changes in the diff

For apps NOT affected by the diff:

- Do NOT load or run their sub-skill. Do NOT run their flows. Do NOT run their pre-flight checks. They are completely out of scope.

If NO app is affected by the diff (e.g., docs-only, CI-only, or config-only changes), report as INCONCLUSIVE: "No app code changed — QA not applicable for this diff." Do NOT run any app flows.

## Step 4: Pre-flight Checks (app-specific only)

Run pre-flight checks ONLY for apps affected by the diff:

- Verify `pip install -e '.[dev]'` succeeds
- Verify the `copilot` CLI entry point is available
- Verify required environment variables are set (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, LLM_API_KEY, LLM_BASE_URL)
  - If any are missing, note them but still proceed — Reddit scraper skips gracefully without creds

Do NOT run pre-flight checks for apps that are NOT affected. If a pre-flight check fails, report it as BLOCKED with the specific error and remediation steps — but still proceed with other affected apps.

## Step 5: Execute Diff-Relevant Flows Only

Read the affected sub-skill from its SKILL.md. Run ONLY the flows that are relevant to the diff:

1. Read the diff carefully and identify which flows match the change
2. Run those flows PLUS any adjacent flows that verify the change integrates correctly
3. Do NOT run completely unrelated flows
4. If no existing flow covers the change, write a NEW ad-hoc test that directly verifies the changed behavior
5. Do NOT run unit tests, lint, typecheck, or any automated test suite

## Step 6: Evidence Capture

For CLI/TUI apps (tuistory):

- Use tuistory to capture terminal state as text snapshots
- Embed snapshots directly in the report as fenced code blocks with descriptive labels
- Each snapshot MUST show something DIFFERENT. Wait for the UI to change before capturing again.

Evidence quality rules:

- Focus on the RELEVANT content. Trim snapshots to the meaningful part.
- Label each snapshot clearly: what it shows and why it matters for the test.
- The workflow uploads all files in `./qa-results/` as a downloadable artifact.

## Step 7: Test Quality Gate

TEST QUALITY REQUIREMENTS:

1. CHANGE-SPECIFIC FIRST. Prioritize tests that directly verify the behavioral change in the diff.
2. INTEGRATION TESTS ARE VALID. Tests that verify the change integrates correctly with existing features are good.
3. NO UNRELATED FLOWS. Do NOT test features completely unrelated to the diff.
4. NO AUTOMATED TEST SUITES. Do NOT run pytest, or any CI-style checks. This is manual/functional QA only.
5. NEGATIVE TESTS. Include at least 1 test verifying error handling or boundary conditions related to the change.
6. INTERACTIVE TESTING. Test by actually interacting with the CLI as a real user would.
7. INCONCLUSIVE IF UNSURE. If you cannot articulate what the changes do, mark as INCONCLUSIVE rather than PASS.

## Step 8: Handle Failures

**Never silently skip a flow.** If a flow cannot complete, report it as BLOCKED with what was tried and how the user can fix it. Then continue to the next flow — never abort the entire run for a single failure.

## Step 9: Generate Report

Generate the report at `./qa-results/report.md` using `.factory/skills/qa/REPORT-TEMPLATE.md`.

The report MUST follow the template. Key rules:

- Start with `## QA Report` heading followed by the test results table
- Result column MUST use emojis: :white_check_mark: PASS, :x: FAIL, :no_entry: BLOCKED, :warning: FLAKY, :grey_question: INCONCLUSIVE
- Keep it CONCISE. The table + a short "Action Required" section (if any) + collapsed evidence = the entire report.
- Do NOT include: "Behavioral Change Summary", "Blocked Flows" prose, "Info" metadata table, or verbose explanations of what the diff does.
- Do NOT report setup/prerequisite steps (building, startup) as test rows.
- Put ALL evidence in a single collapsed `<details>` block
- Embed TUI text snapshots as labeled fenced code blocks

## Step 10: Suggest Skill Updates (Failure Learning)

After generating the report, check if any BLOCKED or FAIL results revealed a **testing environment insight** that would help future QA runs succeed.

**Good suggestions** (environment/workflow knowledge):
- "Feature flag X must be enabled before testing this flow"
- "The Reddit API requires both dev and prod app registrations"
- "G2 rate-limits at 5 pages; increase wait between requests to 3s"

**Bad suggestions** (do NOT suggest these):
- Selector/command typos — fix those directly
- Expected behavior changes from the PR diff

Format as a table with severity and collapsible fix prompts. Only include if genuinely new environment insights were discovered.

Since `failure_learning` is `suggest_in_report`, include the table in the PR comment report only. Do NOT write `skill-updates.json`.
