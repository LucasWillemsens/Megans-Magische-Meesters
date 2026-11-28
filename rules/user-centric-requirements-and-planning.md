## Strictness
2

## Scope
repo wide

## Description
Requirements, plans, and their verification are user-centric: each speaks in terms of what the user sees and can do, never in terms of the implementation or restated code. Requirements originate with the user: agent-derived scoping is never encoded as agreed specification; user input is preserved and unresolved choices are marked open. Roadmap descriptions and their acceptance criteria specify user-visible, checkable behavior that survives renames; naming files and describing seams and concerns is the allowed specificity, and a one-line fix never becomes a roadmap entry. Testing is the art of having less: it is not encouraged. The exceptions are meaningful end-to-end tests and cleaning up or merging existing tests into more meaningful ones; unit tests are near-useless beyond the coding agent verifying itself. A test that is kept is meaningful: it asserts what the user sees — rendered, observable behavior that survives renames — never the literal text of sources or markup shells.

## Context
- The agent-loops goal's PR #31 review: empty deck-indicator li elements kept layout machinery and shell assertions green after the visual content vanished
- The pr-35-polish goal's PR #36 review: 58 assertIn assertions in MMM/tests.py pin literal JS/CSS text while styling-only commits broke about 20 percent of the suite, and description.txt files became patch manuals — paste-ready code blocks, line-number anchors, and pinned CSS/JS values: a 74-line pre-baked patch for a self-described one-line fix and sibling goals carrying contradictory pinned CSS contracts
- The painted-pillars-site goal's PR #32 review: agent-authored plans treated an inferred snapshot window and a frozen four-page scope as agreed requirements and reinterpreted the requested visual composition, until the reviewer corrected the archive research to one page per archived post — proved substance of this rule and was absorbed into it (2026-11-25)
