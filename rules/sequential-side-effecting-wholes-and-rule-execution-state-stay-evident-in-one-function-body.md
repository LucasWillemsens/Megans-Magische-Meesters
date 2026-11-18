## Strictness
1

## Scope
task specific: coding

## Description
When code executes a rule — a game rule, turn limit, validation, or any enforced policy — the rule's execution state is evident from the function body: a reader sees what is being applied and what it currently allows or blocks without chasing helpers. Operations that follow sequentially in logic and form one whole follow sequentially in one function body as well; they are not separated into small functions that are merely called one after another. Pure functions can be greatly factored out of large functions, but a function with side effects is factored out only when it is duplicated multiple times and handles program state very intuitively, like opening or closing a file.

## Context
- User request while building the agent memory ladder and coding skill (2026-11-11)
