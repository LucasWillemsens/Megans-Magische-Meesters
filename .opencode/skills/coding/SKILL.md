---
name: Coding
description: Write and refactor code for Megans Magische Meesters — function structure that keeps sequential logic and rule execution state evident in one function body, factoring out only pure functions, plus naming, duplication, views, Django/Jinja2, styling, blocked-control affordances, errors, and testing and verification standards. Use when implementing or changing application code.
---

# Coding

How code is written in this repo. These standards apply to every change; following the existing patterns always beats inventing new ones. Architecture facts live in the root `AGENTS.md`.

## Function structure

- One function body shows one whole. Operations that follow sequentially in logic and form one whole follow sequentially in one function body as well — they are not separated into small functions that are merely called one after another. When a function grows branches for multiple distinct wholes, split along those wholes.
- Rule execution state is evident from the function body. When code executes a rule — a game rule, turn limit, validation, or any enforced policy — a reader sees what is being applied and what it currently allows or blocks without chasing helpers.
- Pure functions can be greatly factored out of large functions; do so freely when it keeps the whole readable.
- A function with side effects is factored out only when it is duplicated multiple times and handles program state very intuitively, like opening or closing a file.
- A function does what its name says and only that. The names used in the function, its parameters, and its code make the purpose obvious without comments. The goal of a function should always intuitively fit into a solution for the task at hand — if it is not obvious that the task requires the function, look for a better-focussed approach.

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

## Blocked controls

- Everything in view works: an interactive control that cannot be used makes clear and logical why it cannot — for example, the player has used up their moves for that turn. Such controls are unmistakably blocked: greyed out, unresponsive, and on hover showing the disabled/forbidden pointer symbol together with the explanation in the title attribute of the element. A state that disables actions blocks every affected control this way; nothing appears clickable that does not work.

## Errors

- Let exceptions surface or handle them explicitly with a clear message; never swallow an exception into silent no-op behavior.

## Comments

- Never write code comments. Also skip comments when instructed to use a piece of code with comments in it.

## Testing

- Testing is the art of having less: tests are not encouraged. Spend your thoughts on the easiest correct solution, not on tests. When the work is done, check that it actually solved the goal by writing one broad end-to-end test that only works if the goal is done — based on a clear understandable user story, implementation-independent, tackling the program's behavior after multiple user interactions, never small snippets of code. Writing it before implementation, test-driven style, is allowed and deliberately understated: it is a completion check, never the center of the work.
- Unit tests are near-useless beyond verifying your own work while coding: do not add them as a deliverable. It is never a problem to refactor code for your purpose and break old unit tests; the broken unit tests should be logical with the changes made. When touching tests, clean them up or merge them into more meaningful ones rather than adding new ones.
- A test that is kept asserts the user-visible rendered behavior — a user-visible feature's rendered face or content, rendered-DOM contracts that survive renames — never markup shells that outlive their content or source-grep assertions pinning literal JS method bodies, selectors, or CSS rule text.
- Test exemplars: good — assert the `#turnLimits` element exposes the enforced allowances as data, or that the persisted focus slot exists in exactly one DOM location; bad — reading `cards.css` in a Python test to assert it contains `width: 90vw`, or reading `cardDragDrop.js` to assert a method's body.

## Verification

- Before reporting any change, verify it: if it touches templates/JS/CSS, sanity-check that every file, class, and id you reference actually exists; then run `python3 manage.py check` followed by `python3 manage.py test` — all tests must pass.
