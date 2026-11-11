---
name: Rules Management
description: Manage the repo's rules framework — add, update, validate, and implement rules in rules/ with the rules.md version log. Use when adding or changing a rule, checking the rules framework, or deciding where a rule's substance is implemented.
---

# Rules Management

Rules are the value system and the longest form of memory of Megans Magische Meesters: they record what past work learned so it keeps shaping future work. Each rule is one Markdown file in `rules/`; the kebab-case filename is the rule's title, info-dense enough that reading it alone explains the rule. `rules.md` at the repo root is only the version log.

Rules are never placed according to their scope — every rule lives in `rules/`. A rule's scope instead implies where its substance is implemented in agents, so rules keep shaping work without being read:

- `repo wide` → implemented in the root `AGENTS.md`
- `path specific: {PATH}` → implemented in the `AGENTS.md` inside `{PATH}` or its nearest parent directory
- `task specific: {TASK}` → implemented in `.opencode/skills/{TASK}/SKILL.md`, including relevant scripts etc.

Implementations are monitored: the check script below validates the framework mechanically, and whoever manages the rules verifies that each rule's substance is present at its implied location.

## Rule format

```
## Strictness
{number}

## Scope
repo wide | path specific: {PATH} | task specific: {TASK}

## Description
{detailed description of the rule}

## Context
- {relevant goal where the need for this rule became apparent}
```

- **Strictness** is the rule's priority against other rules; when rules conflict, the higher number wins. The number of relevant goals is the heuristic for picking it.
- **Scope** limits the rule to the whole repo, a path, or a task — and implies where the rule's substance is implemented.
- **Context** lists the goals that revealed the need for the rule.

## Adding a rule

```
python3 .opencode/skills/rules-management/scripts/add_rule.py \
    --title <kebab-case-title> --strictness <number> \
    --scope "<scope>" --description "<text>" --context "<goal>" [--context "<goal>" ...]
```

This validates the input, writes `rules/<title>.md`, and appends the v1 entry to the version log. Then implement the rule's substance at the location its scope implies.

## Updating a rule

Edit the rule file, then append the next version entry to the `## Rules version log` section of `rules.md`, dated the same day as the edit. Entries look like `- YYYY-MM-DD — <rule-filename-without-.md> vN`, with ` — <very short explanation>` added for updates; the log runs oldest first, so new entries go at the end. Keep the implementation at the rule's implied location in sync.

## Checking the framework

```
python3 .opencode/skills/rules-management/scripts/check_rules.py
```

Validates that every rule file follows the rule format, that every version log entry is well-formed and oldest first, that every rule's versions run v1..vN without gaps or repeats, that the log and `rules/` agree, that every rule's latest logged version is dated the same day the file was last edited, and that every task-specific rule's skill exists. It also prints the `AGENTS.md` files found inside each path-specific rule's path, or the root `AGENTS.md` fallback.

## Verifying implementations

Implementations never follow a strict structure, so their content cannot be checked programmatically. To truly verify the rules, check the paths the check script outputs: the `AGENTS.md` files inside each path-specific rule's path — the root `AGENTS.md` when the path has none — should include something that satisfies the rule being checked. This takes interpreting both the rule and the `AGENTS.md` instructions, so it is not redone on every check; do it when adding new rules or when updating agents or instructions.
