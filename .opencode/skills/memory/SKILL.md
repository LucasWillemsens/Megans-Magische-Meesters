---
name: Memory
description: Maintain the repo's memory ladder — goal scratchpads, goal-directory lesson logs, and rule candidates co-located with roadmap goals — so insights bubble up between sessions and distill into rules. Use when consolidating a finished goal's scratchpad into lessons, recording PR-review insights into memory files, or promoting rule candidates into rules.
---

# Memory

Insights bubble up between sessions through a ladder of memory files co-located with the roadmap goals that produced them. Each level widens in scope and outlives the one below; each distills into the next:

| Level | File | Scope | Lifetime |
|---|---|---|---|
| Scratchpad | `roadmap/<goal-path>/scratchpad.md` | one goal | current work on the goal |
| Lesson log | `roadmap/<area>/lessons.md` | the goal directory's multiple goals | until promoted |
| Rule candidates | `roadmap/<goal-path>/candidates.md` | one or more PRs against that goal | until promoted or withdrawn |
| Rules | `rules/` + `rules.md` version log | repo / project wide | release versions — the longest memory |

The README generator and CI matcher ignore these files; only `description.txt` counts. Rules are added and versioned through the `rules-management` skill — this ladder only feeds it.

Anyone starting work reads the memory covering their scope: the goal's scratchpad first (where the last session left off), then the goal directory's lesson log. Nothing recorded here overrides the user's direction; memory informs sessions, it does not decide for them.

## Scratchpad format

Newest session first, one dated section per session, short bullets, no narrative:

```markdown
# <goal-name> scratchpad

## YYYY-MM-DD — what this session did
- State: what exists now, what is half-done
- Discovered: code facts, patterns, gotchas
- Decided: choices made and why
- Next: what the following session should pick up
```

Anything that would matter beyond this goal's current work is distilled upward instead of lingering here.

## Consolidating a finished goal

When a delegated goal is implemented and verified:

1. Read the goal's `scratchpad.md` and distill its durable, actionable insights — patterns, pitfalls, conventions discovered — into `roadmap/<area>/lessons.md` as a new dated section `## YYYY-MM-DD — <goal-name>` with one lesson per bullet. Skip what only mattered mid-work.
2. Delete the goal's `scratchpad.md` — short-term memory stays short; git history preserves it.
3. Do not duplicate a lesson already covered by an existing lesson or an implemented rule.

## Recording PR-review insights

After collecting the review analyses for the PR:

1. Determine which roadmap goals the PR worked on — grep the roadmap descriptions for the touched files, or read the README roadmap section.
2. Scratchpad notes: for each touched goal, append a dated session section to its `scratchpad.md` (create it with the format above when absent) listing the concrete fixes the reviewers found, so the next build session starts from them.
3. Lessons: append durable review insights to the touched goals' directories' `lessons.md`, one dated section per goal directory.
4. Rule candidates: when the same problem or pattern recurs across one or more PRs, add it to the `candidates.md` of the deepest goal directory that covers all the evidence — typically `roadmap/<area>/<goal>/candidates.md`, since a PR maps to the goals it touched:

```markdown
# <goal-name> rule candidates

## <pattern-name>
- Pattern: the recurring observation
- Evidence: PR #12, PR #15
- Proposed rule: one sentence
- Status: candidate
```

Cite the PR numbers from the analysts' reports.

## Promoting candidates into rules

1. Glob `roadmap/**/candidates.md` and review candidates with evidence from multiple PRs or clear user endorsement.
2. Propose the promotion to the user — promotion requires their approval.
3. On approval, add the rule through the `rules-management` skill, implement its substance where its scope implies, and set the candidate's Status to `promoted (rule <rule-title> vN)` — or `withdrawn (<reason>)` when rejected.
4. When a lesson log entry becomes a rule, append `→ rule <rule-title> vN` to that lesson so readers know where its substance now lives.

## Monitoring rules

Rules keep shaping work through their implementations in `AGENTS.md` files and skills. The mechanical framework is checked by the `rules-management` check script. Practical adherence is watched where the work happens: PR review records rule violations as lesson entries and candidate evidence, and whoever manages the rules verifies the implementations when agents or instructions change.
