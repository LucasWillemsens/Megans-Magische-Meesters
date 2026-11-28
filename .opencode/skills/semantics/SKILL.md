---
name: Semantics / Language
description: Review and rewrite vague or redundant prose into concrete, checkable statements — undefined pronouns, unquantified claims, terms without definitions, facts stated twice, criteria that contradict the artifact — keeping the author's intent and repo terminology unchanged. Use when tightening agent definitions, skill bodies, roadmap description.txt files, lessons.md, README sections, or any other prose in the repo.
---

# Semantics / Language

How prose is reviewed in this repo: detect vagueness and redundancy, rewrite so a reader can act without guessing, and keep the author's intent unchanged. The review rewords text only — it changes no code, moves no content between files, and flags any passage whose product meaning is unclear instead of deciding it.

## Detect vagueness

A sentence is vague when a reader must guess to act on it:

- **Undefined pronouns** — "it", "this", "that" with more than one candidate referent. Rename test: substitute each candidate for the pronoun; if two substitutions both read naturally but instruct different things, the sentence is ambiguous — pin the referent by name.
- **Unquantified claims** — "often", "many", "soon", "appropriately". State the count, condition, event, or threshold instead; if no concrete instance backs the claim, delete it.
- **Terms with no definition** — a word the repo has not established and the text never defines. Define it at first use or point to the place that defines it. Established terms (`CardState`, lanes, allowances, staged plays, turn limits) need no definition — reuse them exactly rather than coining synonyms.
- **Values and names the artifact contradicts** — every stated value, path, selector, or command must match the file it names; open the artifact before trusting or rewriting the sentence.

## Detect redundancy

A fact stated twice drifts apart, and the reader cannot tell which copy is authoritative:

- **Twice in one document** — e.g. a behavior bullet restated as an acceptance criterion in different words; the copies age differently (the 90vw fault below). Keep the copy where the reader acts on it and delete or reference the other.
- **Across agent, skill, and rule** — a body restating another document's contract rots as the source evolves (roadmap/agent-loops/lessons.md, PR #28); keep a bare pointer to the owning document.
- **Filler phrasing** — "in order to", "it should be noted that", "basically": words carrying no information; delete them.
- **Duplicated criteria** — two checklist items proving the same thing; keep the stronger one.

## Rewrite rules

- One fact stated once, where it is load-bearing — the place the reader must have it to act; everywhere else, point instead of restating.
- Concrete over adjectives: a checkable statement (file, value, command, count, condition) beats "good", "clean", "robust".
- Intent unchanged: clarify what the author wrote; introduce no new requirement, scope, or value.
- Documentation best practices: active voice, present tense, one idea per sentence, definitions before use.
- Keep each document's container format: reword lesson bullets and scratchpad sections, never their dated-section structure; reword an agent's `description`, never its wiring (mode, model, permissions).
- `roadmap/` and `done/` description.txt files feed the README generator and the CI keyword matcher: keep the file paths and feature names that make the item recognizable, and run `python3 scripts/update_roadmap.py` after changing one. Never edit the generated README `## Roadmap` section directly.

## Faults from this repo, before and after

Values below are as of the cited document, not necessarily today's tree — check the artifact before reusing any of them.

1. **A criterion contradicting the artifact.** `done/battle-page-polish/horizontal-lane-spread-20261012/description.txt` pinned criteria and a code inventory at `width: 90vw`, while the shipped `cards.css` rule was `82vw`, recorded only in a parenthetical verification note — a reader executing that checklist would have "fixed" working CSS.
   - Before: "On 4K and larger screens the field scales proportionally to ~90vw (no pixel cap)" — against a shipped `width: 82vw`.
   - After — the pattern the follow-up goal used (`roadmap/pr-35-polish/lanes-layout-contract/description.txt`): "HEAD currently uses `82vw` and `0.5rem` gap, matching neither specification." Check the artifact first, then state the value it actually has. In a done/ entry the request text is history — do not reword it to match; record the shipped state alongside it, as the verification parenthetical does. When the intent is genuinely ambiguous — here the original request was the wider 90vw — flag the conflict for the user; which side carries the intent is a product decision.
2. **Vague delegation vs deterministic wiring.** "The agent figures out which review comment to take each time" assigns judgment with no mechanism, so every run re-derives the choice and runs differ.
   - After (`.opencode/skills/pr-comment-pickup/SKILL.md`): "The script uses authenticated `gh` against the current repository PR ... and immediately resolves one thread before returning it. Do not implement your own PR/comment selection logic." A named script with a stated result replaces per-run judgment.
3. **A criterion naming a nonexistent mechanism.** "Cover the new board interaction in the app's frontend test suite" sends the reader hunting for a runner that does not exist.
   - After (root `AGENTS.md`): "Frontend contract assertions are also in `MMM/tests.py`; there is no separate app frontend test runner." Name the mechanism that exists.

## What this skill does not do

- **No code changes** — prose that contradicts code is flagged with the contradiction; a language review never edits the code.
- **No restructuring** — moving content between files, splitting or merging documents, reordering sections: propose it to the user instead.
- **No intent drift** — when the text's commitment is ambiguous or every faithful wording changes the scope, stop and flag the passage for the user to decide. The author owns what the text means; this skill owns how it says it.
