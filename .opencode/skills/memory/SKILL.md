---
name: Memory
description: Maintain the repo's memory ladder — scratchpads, lesson logs, and rule candidates co-located with roadmap goals. Use when consolidating finished work (a completed goal or thread) into lessons, recording PR-review insights into memory files, or resolving rule candidates into rules.
---

# Memory

Insights bubble up between sessions through a ladder of memory files co-located with the roadmap goals that produced them; each level widens in scope, outlives the one below, and distills into the next:

- `roadmap/<goal-path>/scratchpad.md` — one goal's current work; live state only
- `roadmap/<area>/lessons.md` — the goal directory's multiple goals; until its substance lives in a rule
- `roadmap/<goal-path>/candidates.md` — recurring patterns across PRs against the goal; until resolved: promoted, absorbed, or withdrawn
- `rules/` + `rules.md` version log — repo-wide, release-versioned: the longest memory

Read the memory covering your scope before working — the goal's scratchpad first (where the last session left off), then the goal directory's lessons; memory informs sessions, it never overrides the user's direction. Only `description.txt` counts for the README generator and CI matcher. Rules are added and versioned through the `rules-management` skill — this ladder only feeds it.

## Scratchpad format

Newest session first; one dated section per session — `## YYYY-MM-DD — what this session did` under a `# <goal-name> scratchpad` header in a new file. Four short bullets, no narrative: State (what exists now), Discovered (code facts, patterns, gotchas), Decided (choices and why), Next (what the following session picks up). Anything that would matter beyond this goal's current work is distilled upward instead of lingering here.

## Cleaning up finished work

A scratchpad holds live working state, not an archive of finished work; the record of finished work is its materialized result — code, files, rules, lessons — and git history preserves the rest. When work finishes — a thread completed (fix list implemented, decision enacted, review actions done) or the goal itself implemented and verified — distill the durable insights into `roadmap/<area>/lessons.md` first: one dated section (`## YYYY-MM-DD — <title>`), one lesson per bullet, skipping what only mattered mid-work, never duplicating an existing lesson or an implemented rule. Then:

- Completed thread: delete its dated sections, keeping the newest live state and the next step.
- Finished goal: delete the whole `scratchpad.md`.

Orchestrators delegate either cleanup to the memory agent.

## Recording PR-review insights

After collecting the review analyses for the PR:

1. Find the touched goals — grep the roadmap descriptions for the touched files, or read the README roadmap section.
2. Scratchpad: for each touched goal, append a dated section listing the concrete fixes the reviewers found (create the file with the format above when absent); the cleanup removes them once the fixes are implemented.
3. Lessons: append the durable insights to each touched goal directory's `lessons.md`, one dated section per directory.
4. Rule candidates: for a pattern recurring across one or more PRs, add an entry to the `candidates.md` of the deepest goal directory covering the evidence — `## <pattern-name>` with Pattern, Evidence, and Proposed-rule bullets, citing the PR numbers. First check `rules/`: substance a rule already covers is recorded as a lesson citing that rule — evidence it may need extending — not proposed as a near-duplicate.

## Resolving candidates

1. Glob `roadmap/**/candidates.md` and review candidates with evidence from multiple PRs or clear user endorsement.
2. Check the rule set first: a candidate is ripe for promotion only when no existing rule covers its substance; otherwise propose absorbing it into the covering rule instead of adding a near-duplicate.
3. Propose the resolution to the user — promotion and absorption both require their approval.
4. On approval, run the chosen path through the `rules-management` skill — it adds or extends the rule, implements the substance where the scope implies, and appends the version log entry — then remove the candidate entry: its outcome is recorded by the rule's version log and Context, or as a lesson when withdrawn.
5. Append `→ rule <rule-title> vN` to a lesson whose substance became part of the rule.
