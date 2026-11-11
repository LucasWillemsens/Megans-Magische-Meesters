---
name: Coding
description: Write and refactor code for Megans Magische Meesters — function structure that keeps sequential logic and rule execution state evident in one function body, factoring out only pure functions, plus naming, duplication, views, Django/Jinja2, styling, errors, and testing standards. Use when implementing or changing application code.
---

# Coding

How code is written in this repo. These standards apply to every change; following the existing patterns always beats inventing new ones. Architecture facts live in the root `AGENTS.md`.

## Function structure

- One function body shows one whole. Operations that follow sequentially in logic and form one whole follow sequentially in one function body as well — they are not separated into small functions that are merely called one after another. When a function grows branches for multiple distinct wholes, split along those wholes.
- Rule execution state is evident from the function body. When code executes a rule — a game rule, turn limit, validation, or any enforced policy — a reader sees what is being applied and what it currently allows or blocks without chasing helpers.
- Pure functions can be greatly factored out of large functions; do so freely when it keeps the whole readable.
- A function with side effects is factored out only when it is duplicated multiple times and handles program state very intuitively, like opening or closing a file.
- A function does what its name says and only that. The names used in the function, its parameters, and its code make the purpose obvious without comments. The goal of a function should always intuitively fit into a solution for the roadmap goal at hand — if it is not obvious that the goal requires the function, look for a better-focussed approach.

## Duplication and simplicity

- Minimal code duplication. When re-using code, try to find a generic solution instead of duplicating logic. Each second time a similar query, response-building block, or template fragment is used, wonder if extracting it into a shared function, helper, macro, or include could improve the maintainability and readability of the code.
- Simplicity first. Write the least code that correctly solves the problem. Delete dead code instead of commenting it out. No speculative abstractions or options nobody asked for.

## Naming

- Descriptive unique short naming. Names say what a thing is or does (`trustable_cards`, not `tc`; `run_bot_turn`, not `process`). No single-letter or abbreviated names outside tight loops. Names include the correct term for the mechanics they are used in and are unique so they are not confused for another parameter. If parameter names are too much alike or parallels of other variables, consider more compact datastructures that merge the multiple variables into one.

## Views and logic modules

- Separate views from logic modules. Views only parse input, call logic, and render/redirect. Models or separate modules define game rules, queries, and state changes are in different files without HTTP machinery.

## Django and Jinja2 specifics

- Keep business logic out of templates (compute in Python, pass plain context). Use `select_related`/`prefetch_related` when looping over related objects. Use `get_object_or_404` for lookups that must exist. Shared template markup goes in Jinja2 macros or includes.

## Styling

- Minimize inline styling — prefer css usage over styling in html. CSS files are logically structured with files scoped to features that require styling. Styling cascades down from generality and importance, with static variables on top for easy customization; the further down in the file, the more specific the styling. Styling is maximally re-used. Refactor styling if css files can be shrunk down without losing maintainability, even if website appearance is impacted. Templates and JS use css classes whenever possible.

## Errors

- Let exceptions surface or handle them explicitly with a clear message; never swallow an exception into silent no-op behavior.

## Comments

- Never write code comments. Also skip comments when instructed to use a piece of code with comments in it.

## Testing

- Write unit tests for new logic to ensure functionality. It is never a problem to refactor code for your purpose and break old unit tests; the broken unit tests should be logical with the changes made. Always make end-to-end tests for new features based on a clear understandable user story that belongs to the roadmap item you are implementing. End-to-end tests maximize implementation-independent solutions so they don't require updates constantly; they are larger and tackle complex behavior of the program after multiple user interactions; they do not test small snippets of code.
