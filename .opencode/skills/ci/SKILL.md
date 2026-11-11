---
name: CI
description: Run the repo's CI pipeline — authorization rules for scripts/ci.py, dry-run previewing, checking output for wrong done/ matches, test failures, README regressions and branch/PR mistakes, and recording manual fixes so the matcher learns. Use when the user asks to run the CI pipeline or authorizes it during implementation.
---

# CI

The CI pipeline (`python3 scripts/ci.py`) matches source changes to roadmap items, updates `done/` and the README, runs tests, and — only when explicitly requested — commits, pushes, and opens a PR.

## Authorization

Run the CI script only when the user explicitly asks to run the pipeline or authorizes it as part of the requested implementation. First inspect its help/options, then run `--dry-run` and review the proposed matches and actions before a run that can commit, push, or open a PR. Do not authorize or initiate those external actions unless the user has asked for that pipeline outcome.

When authorized, run:

```
python3 scripts/ci.py
```

The script may automate:
1. Checking git status and current changes
2. Matching source code changes against roadmap descriptions
3. Updating the `done/` directory for matched items
4. Running tests (`python manage.py test`)
5. Running `python3 scripts/update_roadmap.py` to refresh the README
6. Committing, pushing to a feature branch, and opening a PR

## Check the output for obvious mistakes

Inspect the script's output and resulting changes; do not treat a successful exit as proof that every result is correct. Check:

- **Wrong done/ matches** — the keyword matcher can credit the wrong roadmap item. Correct or exclude unrelated matches during the preview, before running the committing pipeline.
- **Test failures** — the script aborts on failing tests; fix the cause (or ask the user) before re-running.
- **README regressions** — skim the regenerated roadmap section for empty headings or items listed under the wrong heading.
- **Branch/PR mistakes** — steer with `--branch <name>` when the default branch is wrong, and preview with `--dry-run` when unsure.

## Record manual fixes so the CI learns

The CI script has a **self-improvement** system that learns from manual corrections. Whenever you have to fix a mistake the CI script generated (especially false-positive `done/` matches), **record the correction so the CI learns from it**:

1. After manually removing a falsely matched `done/` entry, run:
   ```
   python3 scripts/ci.py --record-fix <roadmap-path> "<comma-separated keywords that caused the false match>"
   ```
   This records which keywords were misleading and updates a persistent blocklist.

2. To see past corrections and what the CI has learned:
   ```
   python3 scripts/ci.py --list-fixes
   ```

3. If you need to reset the learned blocklist (keeping raw fix records):
   ```
   python3 scripts/ci.py --reset-blocklist
   ```

**How the learning works internally:**
- Recorded false-positive keywords are added to a blocklist in `ci_fixes/false_positive_blocklist.json`.
- Future CI runs use this blocklist to:
  - De-boost match scores that rely on blocked keywords.
  - Completely suppress matches on paths that were previously false positives.
  - Suppress specific (keyword, path) pairs that have caused false matches.
- The `MATCH_THRESHOLD` also increases dynamically (by 0.02 per correction, up to +0.10 max), forcing higher confidence for auto-additions.

**Always record a fix after correcting a CI mistake.** This makes the CI smarter over time and reduces the need for repeated manual fixes of the same kind.

## After an external run

If an authorized run pushes changes or opens a PR, review the resulting diff and PR details where available, then report the branch, PR, and any concerns to the user.
