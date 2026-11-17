## Strictness
1

## Scope
task specific: coding

## Description
When code executes a rule — a game rule, turn limit, validation, or any enforced policy — the rule's execution state is evident from the function body: a reader sees what is being applied and what it currently allows or blocks without chasing helpers. Operations that follow sequentially in logic and form one whole follow sequentially in one function body as well; they are not separated into small functions that are merely called one after another. Pure functions can be greatly factored out of large functions, but a function with side effects is factored out only when it is duplicated multiple times and handles program state very intuitively, like opening or closing a file. Code, including styling, is effective without side effects: updating styling in a generic setting — a shared or global class such as `.players`, `.title`, or `.backlink` — logically changes more than one page, so every template using the class is accounted for before its global styling changes; when the styling of one page changes and unexpectedly breaks another, that hidden side effect warrants a refactoring with the goal to make everything more compact, structured, and readable, scoping page-specific looks with explicit classes carried in that page's template (like `.demoTitle`) instead of structural exception lists (`body:has(> .fullpage-background)`) and keeping shared components consistent across pages — the same principle as rule execution state staying evident in one function body.

## Context
- User request while building the agent memory ladder and coding skill (2026-11-11)
- The pre-battle-deck-flow goal's PR #28 review — its shared-styling-across-pages candidate proved to be substance of this rule and was absorbed into it (2026-11-17)
